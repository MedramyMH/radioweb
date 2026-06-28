import os
import logging
import re
import httpx
from typing import List, Dict, Optional
from enum import Enum
from urllib.parse import urlparse, parse_qs

try:
    from faster_whisper import WhisperModel
except ImportError as exc:
    WhisperModel = None
    _faster_whisper_import_error = exc

logger = logging.getLogger(__name__)

class ModelSize(str, Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"

MODEL_DIR = os.getenv("MODEL_DIR", "/tmp/whisper_models")
os.makedirs(MODEL_DIR, exist_ok=True)

_models: Dict[str, WhisperModel] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# YOUTUBE CAPTION FETCHING (FASTEST - NO DOWNLOAD)
# ═══════════════════════════════════════════════════════════════════════════════

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/shorts\/|youtube\.com\/live\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

async def fetch_youtube_captions_innertube(video_id: str, language: str = "en") -> Optional[List[Dict]]:
    """
    Fetch YouTube captions using Innertube API (MUCH FASTER - no video download).
    
    This is the KEY OPTIMIZATION from the YouTube transcriber app!
    
    Args:
        video_id: YouTube video ID
        language: Language code (ar, en, fr, etc.)
        
    Returns:
        List of segments with timestamps and text, or None if no captions found
    """
    logger.info(f"Attempting to fetch captions for video {video_id} (language: {language})")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # YouTube Innertube API request
            response = await client.post(
                "https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
                json={
                    "context": {
                        "client": {
                            "clientName": "ANDROID",
                            "clientVersion": "20.10.38"
                        }
                    },
                    "videoId": video_id,
                },
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0"
                }
            )
            
            data = response.json()
            tracks = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
            
            if not tracks:
                logger.info(f"No captions found for video {video_id}")
                return None
            
            # Try to find caption track in preferred language
            track = None
            
            # Priority: exact language match → ar → en → first available
            for t in tracks:
                if t.get("languageCode", "").startswith(language):
                    track = t
                    break
            
            if not track:
                for t in tracks:
                    if t.get("languageCode", "").startswith("ar"):
                        track = t
                        break
            
            if not track:
                for t in tracks:
                    if t.get("languageCode", "").startswith("en"):
                        track = t
                        break
            
            if not track:
                track = tracks[0]
            
            base_url = track.get("baseUrl")
            if not base_url:
                logger.warning(f"No baseUrl found in caption track")
                return None
            
            # Fetch caption data in JSON3 format (cleaner than XML)
            logger.info(f"Fetching caption data from: {base_url[:50]}...")
            captions_response = await client.get(f"{base_url}&fmt=json3")
            captions_data = captions_response.json()
            
            if not isinstance(captions_data.get("events"), list):
                logger.warning("Invalid caption data structure")
                return None
            
            # Parse caption segments
            segments = []
            for event in captions_data["events"]:
                segs = event.get("segs", [])
                if not segs:
                    continue
                
                # Combine all text in this event
                text = "".join(seg.get("utf8", "") for seg in segs).strip()
                if not text:
                    continue
                
                start_time = (event.get("tStartMs", 0) or 0) / 1000  # Convert ms to seconds
                
                # Calculate approximate duration (for last segment, assume 5 seconds)
                next_event = None
                current_idx = captions_data["events"].index(event)
                if current_idx + 1 < len(captions_data["events"]):
                    next_event = captions_data["events"][current_idx + 1]
                
                if next_event:
                    duration = (next_event.get("tStartMs", start_time * 1000) or start_time * 1000) / 1000 - start_time
                else:
                    duration = 5.0  # Default duration for last segment
                
                segments.append({
                    "start": max(0, start_time),
                    "end": max(0, start_time + duration),
                    "text": text,
                    "duration": max(0.1, duration)
                })
            
            if segments:
                logger.info(f"✅ Successfully fetched {len(segments)} caption segments from YouTube (no download needed!)")
                return segments
            else:
                logger.info(f"No caption segments could be parsed")
                return None
                
    except Exception as e:
        logger.warning(f"Failed to fetch captions from Innertube API: {str(e)}")
        return None

async def fetch_youtube_captions_transcript_ai(video_id: str) -> Optional[List[Dict]]:
    """
    Fallback: Fetch captions from youtube-transcript.ai API (public endpoint).
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        List of segments with timestamps and text, or None if no captions found
    """
    logger.info(f"Trying youtube-transcript.ai for video {video_id}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://youtube-transcript.ai/transcript/{video_id}.txt",
                follow_redirects=True
            )
            
            if response.status_code != 200:
                logger.info(f"youtube-transcript.ai returned {response.status_code}")
                return None
            
            text = response.text
            segments = parse_plain_text_into_segments(text)
            
            if segments:
                logger.info(f"✅ Fetched {len(segments)} segments from youtube-transcript.ai")
                return segments
            
            return None
            
    except Exception as e:
        logger.warning(f"youtube-transcript.ai failed: {str(e)}")
        return None

def parse_plain_text_into_segments(text: str) -> List[Dict]:
    """
    Parse plain text transcript into segments with timestamps.
    
    Handles formats like:
    - [00:00.000 -> 00:05.000] text
    - [0:00 -> 0:05] text
    - 00:00 text
    """
    lines = text.replace("&gt;", ">").replace("&lt;", "<").split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    
    segments = []
    
    for i, line in enumerate(lines):
        # Format: [start -> end] text
        match = re.match(
            r'^\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*[-–>]+\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]\s*(.*)$',
            line
        )
        if match:
            start = parse_seconds(match.group(1))
            end = parse_seconds(match.group(2))
            text = match.group(3).strip()
            segments.append({
                "start": start,
                "end": end,
                "text": text,
                "duration": end - start
            })
            continue
        
        # Format: HH:MM:SS text
        match = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)$', line)
        if match:
            start = parse_seconds(match.group(1))
            text = match.group(2).strip()
            segments.append({
                "start": start,
                "end": start + 5,  # Assume 5 second duration
                "text": text,
                "duration": 5.0
            })
            continue
        
        # Just text with no timestamp
        if line:
            segments.append({
                "start": i * 5,
                "end": (i + 1) * 5,
                "text": line,
                "duration": 5.0
            })
    
    return segments

def parse_seconds(timestamp: str) -> float:
    """Parse timestamp string to seconds."""
    timestamp = timestamp.replace(",", ".").strip()
    parts = [float(x) for x in timestamp.split(":")]
    
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    else:
        return parts[0] if parts else 0

# ═══════════════════════════════════════════════════════════════════════════════
# WHISPER TRANSCRIPTION (FALLBACK - WHEN NO CAPTIONS EXIST)
# ═══════════════════════════════════════════════════════════════════════════════

def get_model(model_size: str = "base") -> WhisperModel:
    """Get or load a Whisper model with caching."""
    if WhisperModel is None:
        raise ImportError(f"faster_whisper is not installed. {_faster_whisper_import_error}")
    
    valid_sizes = [e.value for e in ModelSize]
    if model_size not in valid_sizes:
        raise ValueError(f"Invalid model size: {model_size}. Must be one of {valid_sizes}")
    
    if model_size not in _models:
        logger.info(f"Loading Whisper model: {model_size}")
        try:
            _models[model_size] = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                download_root=MODEL_DIR
            )
            logger.info(f"✅ Loaded model: {model_size}")
        except Exception as e:
            logger.error(f"Failed to load model {model_size}: {str(e)}")
            raise
    
    return _models[model_size]

def transcribe_audio(
    file_path: str,
    language: Optional[str] = None,
    model_size: str = "base",
    beam_size: int = 5,
    best_of: int = 5
) -> List[Dict]:
    """
    Transcribe audio file using Whisper (FALLBACK).
    
    Use this only when captions are not available!
    
    Args:
        file_path: Path to audio file
        language: Language code
        model_size: Whisper model size
        beam_size: Beam search width
        best_of: Number of candidates
        
    Returns:
        List of segment dictionaries
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    logger.info(f"🎤 Transcribing audio with Whisper: {file_path} (model: {model_size})")
    
    try:
        model = get_model(model_size)
        
        transcribe_options = {
            "beam_size": beam_size,
            "best_of": best_of,
        }
        
        if language and language != "auto":
            transcribe_options["language"] = language
        
        segments, info = model.transcribe(file_path, **transcribe_options)
        
        results = []
        for segment in segments:
            results.append({
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "duration": float(segment.end - segment.start)
            })
        
        logger.info(f"✅ Whisper transcription complete: {len(results)} segments (language: {info.language})")
        return results
        
    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        raise RuntimeError(f"Transcription failed: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def get_full_transcript(segments: List[Dict]) -> str:
    """Convert segments to full text transcript."""
    return " ".join([s.get("text", "") for s in segments if s.get("text")])

def get_transcript_with_timestamps(segments: List[Dict]) -> str:
    """Convert segments to transcript with timestamps."""
    lines = []
    for seg in segments:
        start = format_timestamp(seg.get("start", 0))
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{start}] {text}")
    
    return "\n".join(lines)

def format_timestamp(seconds: float) -> str:
    """Format seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
    else:
        return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"

def unload_model(model_size: str = "base") -> None:
    """Unload a cached model to free memory."""
    if model_size in _models:
        del _models[model_size]
        logger.info(f"Unloaded model: {model_size}")

def unload_all_models() -> None:
    """Unload all cached models to free memory."""
    _models.clear()
    logger.info("Unloaded all models")

def get_loaded_models() -> List[str]:
    """Get list of currently loaded models."""
    return list(_models.keys())