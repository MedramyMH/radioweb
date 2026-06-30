import os, uuid, asyncio
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.services.media_service import (
    get_video_metadata, process_editor_actions, TEMP_DIR
)
from app.services.downloader_service import get_available_formats, download_media

router = APIRouter()

def cleanup_file(path: str):
    if os.path.exists(path):
        try: os.remove(path)
        except: pass

@router.get("/downloader")
async def downloader_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request, "downloader.html", {"request": request})

@router.post("/api/editor/get-formats")
async def get_formats(url: str = Form(...)):
    """
    Fetch available formats without downloading.
    Returns video and audio format options with qualities.
    """
    try:
        formats = await asyncio.to_thread(get_available_formats, url)
        return formats
    except Exception as e:
        raise HTTPException(400, f"Invalid URL or format extraction failed: {str(e)}")

@router.post("/api/editor/download-format")
async def download_selected_format(
    url: str = Form(...),
    format_id: str = Form(...),
    format_type: str = Form(...)  # 'video' or 'audio'
):
    """
    Download the video with the selected format_id.
    Returns the temporary file path for the editor.
    """
    job_id = str(uuid.uuid4())
    temp_path = str(TEMP_DIR / f"{job_id}_temp")
    
    try:
        # Create temp directory if it doesn't exist
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        # Download with selected format
        await asyncio.to_thread(download_media, url, format_id, str(TEMP_DIR) + "/")
        
        # Get the downloaded file (yt_dlp saves with video id)
        # Find the file that was just downloaded
        for file in os.listdir(TEMP_DIR):
            file_path = str(TEMP_DIR / file)
            # Skip if it's a directory or our job tracking
            if os.path.isfile(file_path) and file.startswith(job_id) is False:
                # Rename to our standard format
                if format_type == 'audio':
                    final_path = str(TEMP_DIR / f"{job_id}.m4a")
                else:
                    final_path = str(TEMP_DIR / f"{job_id}.mp4")
                
                os.rename(file_path, final_path)
                
                # If it's a video, get metadata
                if format_type == 'video':
                    meta = await asyncio.to_thread(get_video_metadata, final_path, job_id)
                    return {
                        "job_id": job_id,
                        "duration": meta["duration"],
                        "thumbnail": meta["thumbnail"],
                        "format_type": "video"
                    }
                else:
                    # For audio, we don't need metadata
                    return {
                        "job_id": job_id,
                        "format_type": "audio"
                    }
        
        raise Exception("Downloaded file not found")
        
    except Exception as e:
        if os.path.exists(temp_path):
            cleanup_file(temp_path)
        raise HTTPException(500, f"Download failed: {str(e)}")

@router.post("/api/editor/load")
async def load_video_to_editor(
    request: Request, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(None)
):
    """
    Load a locally uploaded file to the editor.
    """
    job_id = str(uuid.uuid4())
    video_path = None
    
    try:
        if file:
            video_path = str(TEMP_DIR / f"{job_id}_{file.filename}")
            with open(video_path, "wb") as f:
                f.write(await file.read())
        else:
            raise HTTPException(400, "Provide a file")

        # Rename to standard job_id.mp4 for easy tracking
        final_path = str(TEMP_DIR / f"{job_id}.mp4")
        if video_path != final_path:
            os.rename(video_path, final_path)
            video_path = final_path

        # Extract metadata (duration, thumbnail)
        meta = await asyncio.to_thread(get_video_metadata, video_path, job_id)
        
        return {"job_id": job_id, "duration": meta["duration"], "thumbnail": meta["thumbnail"], "format_type": "video"}

    except Exception as e:
        if video_path and os.path.exists(video_path): cleanup_file(video_path)
        raise HTTPException(500, str(e))

@router.post("/api/editor/export")
async def export_video(
    request: Request,
    background_tasks: BackgroundTasks,
    job_id: str = Form(...),
    start_time: float = Form(0.0),
    end_time: float = Form(None),
    volume: float = Form(1.0),
    speed: float = Form(1.0)
):
    """
    Export edited video with applied effects.
    """
    video_path = str(TEMP_DIR / f"{job_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(404, "Video session expired or not found")

    output_path = None
    try:
        output_path = await asyncio.to_thread(
            process_editor_actions, 
            video_path, 
            start_time, 
            end_time, 
            volume, 
            speed
        )
        background_tasks.add_task(cleanup_file, video_path)
        background_tasks.add_task(cleanup_file, output_path)
        
        return FileResponse(output_path, filename=f"edited_{job_id}.mp4", background=background_tasks)
    except Exception as e:
        raise HTTPException(500, str(e))
