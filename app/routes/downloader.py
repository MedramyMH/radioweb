import os, uuid, asyncio
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.services.media_service import (
    download_media, get_video_metadata, process_editor_actions, TEMP_DIR
)

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

@router.post("/api/editor/load")
async def load_video_to_editor(
    request: Request, 
    background_tasks: BackgroundTasks,
    url: str = Form(None), 
    file: UploadFile = File(None)
):
    job_id = str(uuid.uuid4())
    video_path = None
    
    try:
        if url:
            video_path = await asyncio.to_thread(download_media, url, "mp4")
            video_path = video_path["filepath"]
        elif file:
            video_path = str(TEMP_DIR / f"{job_id}_{file.filename}")
            with open(video_path, "wb") as f:
                f.write(await file.read())
        else:
            raise HTTPException(400, "Provide URL or File")

        # Rename to standard job_id.mp4 for easy tracking
        final_path = str(TEMP_DIR / f"{job_id}.mp4")
        if video_path != final_path:
            os.rename(video_path, final_path)
            video_path = final_path

        # Extract metadata (duration, thumbnail)
        meta = await asyncio.to_thread(get_video_metadata, video_path, job_id)
        
        return {"job_id": job_id, "duration": meta["duration"], "thumbnail": meta["thumbnail"]}

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
