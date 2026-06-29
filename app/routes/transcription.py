import os
import uuid
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services.transcription_service import (
    extract_youtube_id,
    fetch_youtube_captions_innertube,
    fetch_youtube_captions_transcript_ai,
    transcribe_audio,
    get_full_transcript,
    get_transcript_with_timestamps,
    get_loaded_models,
    unload_all_models,
    ModelSize
)
import yt_dlp

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ─────────────────────────────────────────────────────────────────────────────
# File utilities
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_file(path: str) -> bool:
    """Safely remove a file."""
    if not path or not os.path.exists(path):
        return False
    
    try:
        os.remove(path)
        logger.info(f"Cleaned up file: {path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to cleanup file {path}: {str(e)}")
        return False

def get_temp_path(filename: str = "") -> str:
    """Generate a safe temporary file path."""
    file_id = str(uuid.uuid4())
    if filename:
        ext = os.path.splitext(filename)[1]
        return f"/tmp/{file_id}{ext}"
    return f"/tmp/{file_id}"

# ─────────────────────────────────────────────────────────────────────────────
# YouTube Smart Handling (Caption Fetching - NO DOWNLOAD!)
# ─────────────────────────────────────────────────────────────────────────────

async def process_youtube_url(
    url: str,
    language: str = "en",
    model: str = "base"
) -> tuple:
    """
    ⚡ SMART YOUTUBE PROCESSING ⚡
    
    1. Try to fetch existing captions (INSTANT, no download)
    2. Only download audio if captions don't exist (fallback)
    
    Returns:
        (segments, source) where source is "captions" or "whisper"
    """
    logger.info(f"Processing YouTube URL: {url}")
    
    # Extract video ID
    video_id = extract_youtube_id(url)
    if not video_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL format"
        )
    
    logger.info(f"YouTube Video ID: {video_id}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: Try to fetch captions (INSTANT - no download!)
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.info("📺 Attempting to fetch existing YouTube captions...")
    
    # Try Innertube API first
    segments = await fetch_youtube_captions_innertube(video_id, language)
    
    # If that fails, try youtube-transcript.ai
    if not segments:
        logger.info("⚙️ Innertube failed, trying youtube-transcript.ai...")
        segments = await fetch_youtube_captions_transcript_ai(video_id)
    
    # Captions found! Return immediately
    if segments:
        logger.info(f"✅ Got captions without downloading! Returning {len(segments)} segments")
        return segments, "captions"
    
    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: No captions found - Download and use Whisper (fallback)
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.warning(f"⚠️ No captions found. Falling back to audio download + Whisper transcription...")
    logger.warning(f"This will take longer and use more memory/bandwidth.")
    
    # Download audio
    temp_path = await download_audio_from_url(url, file_format="mp3", timeout=120)
    
    try:
        # Transcribe with Whisper
        segments = await asyncio.to_thread(
            transcribe_audio,
            temp_path,
            language=language if language != "auto" else None,
            model_size=model,
            beam_size=5,
            best_of=5
        )
        
        return segments, "whisper"
        
    finally:
        # Cleanup audio file
        cleanup_file(temp_path)

async def download_audio_from_url(
    url: str,
    file_format: str = "mp3",
    timeout: int = 120
) -> str:
    """
    Download audio from URL using yt-dlp.
    
    This is a FALLBACK - only used when captions don't exist!
    """
    file_id = str(uuid.uuid4())
    outtmpl = f"/tmp/{file_id}.%(ext)s"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'quiet': False,
        'socket_timeout': timeout,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    if file_format.lower() in ['mp3', 'wav', 'm4a', 'opus']:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': file_format.lower(),
            'preferredquality': '192'
        }]
    
    logger.warning(f"⏬ Downloading audio from {url[:50]}... (this takes time!)")
    
    try:
        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return f"/tmp/{file_id}.{file_format.lower()}"
        
        temp_path = await asyncio.to_thread(_download)
        
        if not os.path.exists(temp_path):
            raise RuntimeError(f"Download completed but file not found: {temp_path}")
        
        file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        logger.info(f"✅ Audio downloaded: {file_size_mb:.2f} MB")
        
        return temp_path
        
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {str(e)}")
        raise RuntimeError(f"Failed to download audio: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during download: {str(e)}")
        raise RuntimeError(f"Audio download failed: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/transcription", response_class=HTMLResponse)
async def transcription_page(request: Request):
    """Serve the transcription UI page."""
    return templates.TemplateResponse(request, "transcription.html")

@router.post("/api/transcribe")
async def api_transcribe(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(None),
    url: str = Form(None),
    language: str = Form("en"),
    model: str = Form("base"),
    timestamps: bool = Form(False),
):
    """
    🚀 SMART TRANSCRIPTION ENDPOINT 🚀
    
    For YouTube URLs:
    1. Tries to fetch captions FIRST (instant, no download)
    2. Only downloads audio if captions don't exist (fallback)
    
    For file uploads:
    - Transcribes directly with Whisper
    
    Args:
        file: Audio file upload (optional)
        url: YouTube URL or direct audio URL (optional)
        language: Language code (en, ar, auto, etc.)
        model: Model size (tiny, base, small, medium)
        timestamps: Include timestamps in output
        
    Returns:
        Rich JSON response with transcript and metadata
    """
    temp_path = None
    
    try:
        # Validate inputs
        if not file and not url:
            raise HTTPException(
                status_code=400,
                detail="Provide either a file upload or a URL"
            )
        
        # Validate model
        valid_models = [e.value for e in ModelSize]
        if model not in valid_models:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model: {model}. Must be one of {valid_models}"
            )
        
        language = language.strip().lower() if language else "en"
        
        logger.info(f"Transcription request: model={model}, language={language}")
        
        # ─────────────────────────────────────────────────────────────────────
        # HANDLE REQUEST
        # ─────────────────────────────────────────────────────────────────────
        
        source = None  # Track whether captions or whisper was used
        
        if url:
            # Check if it's a YouTube URL
            if "youtube.com" in url or "youtu.be" in url:
                logger.info("🎬 YouTube URL detected - using smart caption fetching!")
                segments, source = await process_youtube_url(url, language, model)
            else:
                # Regular URL (direct audio)
                logger.info("📡 Direct URL - downloading audio...")
                temp_path = await download_audio_from_url(url, file_format="mp3", timeout=120)
                segments = await asyncio.to_thread(
                    transcribe_audio,
                    temp_path,
                    language=language if language != "auto" else None,
                    model_size=model,
                    beam_size=5,
                    best_of=5
                )
                source = "whisper"
        
        elif file:
            # File upload
            temp_path = get_temp_path(file.filename)
            logger.info(f"📁 Processing uploaded file: {file.filename}")
            
            try:
                with open(temp_path, "wb") as buffer:
                    contents = await file.read()
                    buffer.write(contents)
                
                file_size_mb = len(contents) / (1024 * 1024)
                logger.info(f"File saved: {file_size_mb:.2f} MB")
                
            except Exception as e:
                cleanup_file(temp_path)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to save uploaded file: {str(e)}"
                )
            
            # Transcribe
            segments = await asyncio.to_thread(
                transcribe_audio,
                temp_path,
                language=language if language != "auto" else None,
                model_size=model,
                beam_size=5,
                best_of=5
            )
            source = "whisper"
        
        # ─────────────────────────────────────────────────────────────────────
        # FORMAT OUTPUT
        # ─────────────────────────────────────────────────────────────────────
        
        if not segments:
            raise HTTPException(
                status_code=500,
                detail="No transcription results"
            )
        
        full_text = get_full_transcript(segments)
        
        if not full_text.strip():
            raise HTTPException(
                status_code=500,
                detail="No transcribable content detected"
            )
        
        total_duration = sum(s.get("duration", 0) for s in segments)
        word_count = len(full_text.split())
        
        response_data = {
            "text": full_text,
            "segments": segments,
            "language": language,
            "model": model,
            "word_count": word_count,
            "duration": float(total_duration),
            "segment_count": len(segments),
            "source": source,  # 🔑 NEW: Show whether captions or Whisper was used
        }
        
        if timestamps:
            response_data["formatted"] = get_transcript_with_timestamps(segments)
        
        # ─────────────────────────────────────────────────────────────────────
        # CLEANUP & RESPOND
        # ─────────────────────────────────────────────────────────────────────
        
        if temp_path:
            background_tasks.add_task(cleanup_file, temp_path)
        
        # Log processing details
        if source == "captions":
            logger.info(f"✅ Completed using YouTube captions (FAST!) - {word_count} words")
        else:
            logger.info(f"✅ Completed using Whisper transcription (slower) - {word_count} words")
        
        return JSONResponse(response_data)
        
    except HTTPException:
        if temp_path:
            cleanup_file(temp_path)
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        if temp_path:
            cleanup_file(temp_path)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )

@router.get("/api/models")
async def get_available_models():
    """Get list of available Whisper models."""
    return JSONResponse({
        "available": [e.value for e in ModelSize],
        "loaded": get_loaded_models(),
        "descriptions": {
            "tiny": "Fastest, ~39M params, lower accuracy",
            "base": "Balanced speed/accuracy (default), ~74M params",
            "small": "Better accuracy, ~244M params, slower",
            "medium": "Best accuracy, ~769M params, slowest"
        }
    })

@router.post("/api/cleanup")
async def cleanup_models():
    """Manually unload all cached models to free memory."""
    try:
        unload_all_models()
        logger.info("All models unloaded")
        return JSONResponse({
            "status": "success",
            "message": "All models unloaded and memory freed"
        })
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )

@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "status": "ok",
        "loaded_models": get_loaded_models()
    })
