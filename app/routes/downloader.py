import os, uuid, asyncio
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.services.media_service import (
    get_video_metadata, process_editor_actions, TEMP_DIR
)
from app.services.downloader_service import get_available_formats, download_media

router = APIRouter()

# Path to cookies file (user can extract from browser)
COOKIES_PATH = os.path.expanduser("~/yt-dlp-cookies.txt")

def cleanup_file(path: str):
    if os.path.exists(path):
        try: os.remove(path)
        except: pass

@router.get("/downloader")
async def downloader_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request, "downloader.html", {"request": request})

@router.get("/api/editor/auth-help")
async def get_auth_help():
    """
    Return authentication help information
    """
    return {
        "auth_required": True,
        "message": "YouTube requires authentication for many videos",
        "solutions": [
            {
                "method": "Use Browser Cookies (Recommended)",
                "steps": [
                    "Install: pip install browser-cookie3",
                    "Log into YouTube in your browser",
                    "Run our cookie extraction tool",
                    "Cookies will be saved automatically"
                ],
                "advantages": "Works seamlessly, fully automated"
            },
            {
                "method": "Manual Cookie Export",
                "steps": [
                    "Install Chrome extension: EditThisCookie",
                    "Go to youtube.com and sign in",
                    "Click EditThisCookie icon",
                    "Click Export and save as cookies.txt",
                    "Place file at: ~/yt-dlp-cookies.txt"
                ],
                "advantages": "Full control, works for signed-in cookies"
            },
            {
                "method": "Use Different Video Source",
                "steps": [
                    "Try another platform: TikTok, Dailymotion, Vimeo",
                    "These usually don't require authentication",
                    "No setup needed"
                ],
                "advantages": "No authentication needed"
            }
        ]
    }

@router.post("/api/editor/get-formats")
async def get_formats(url: str = Form(...)):
    """
    Fetch available formats without downloading.
    Returns video and audio format options with qualities.
    """
    try:
        # Check if cookies file exists
        cookies = COOKIES_PATH if os.path.exists(COOKIES_PATH) else None
        
        formats = await asyncio.to_thread(
            get_available_formats, 
            url,
            cookies
        )
        
        # If auth is required, include helpful message
        if formats.get("auth_required"):
            return {
                **formats,
                "help_url": "/api/editor/auth-help"
            }
        
        return formats
    except Exception as e:
        error_msg = str(e)
        
        # Check if it's an authentication error
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(
                400, 
                {
                    "error": "Authentication Required",
                    "message": "YouTube requires you to sign in. Please extract cookies from your browser.",
                    "help_url": "/api/editor/auth-help",
                    "details": error_msg[:200]
                }
            )
        elif "Unsupported URL" in error_msg or "No video found" in error_msg:
            raise HTTPException(400, f"Invalid or unsupported URL: {error_msg[:200]}")
        else:
            raise HTTPException(400, f"Error: {error_msg[:200]}")

@router.post("/api/editor/extract-cookies")
async def extract_cookies(browser: str = Form("chrome")):
    """
    Extract cookies from browser automatically.
    Supported browsers: chrome, firefox, edge
    """
    try:
        from app.services.downloader_service import extract_cookies_from_browser
        
        cookies_path = await asyncio.to_thread(
            extract_cookies_from_browser,
            browser
        )
        
        if cookies_path and os.path.exists(cookies_path):
            return {
                "success": True,
                "message": f"Cookies extracted from {browser}",
                "cookies_path": cookies_path
            }
        else:
            raise Exception(f"Failed to extract cookies. Make sure you're logged into YouTube in {browser}")
    
    except ImportError:
        raise HTTPException(
            400,
            {
                "error": "Missing dependency",
                "message": "Please install browser-cookie3: pip install browser-cookie3",
                "instructions": "https://github.com/borisbabic/browser_cookie3"
            }
        )
    except Exception as e:
        raise HTTPException(400, str(e))

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
        
        # Check if cookies file exists
        cookies = COOKIES_PATH if os.path.exists(COOKIES_PATH) else None
        
        # Download with selected format
        await asyncio.to_thread(
            download_media, 
            url, 
            format_id, 
            str(TEMP_DIR) + "/",
            cookies
        )
        
        # Get the downloaded file
        for file in os.listdir(TEMP_DIR):
            file_path = str(TEMP_DIR / file)
            if os.path.isfile(file_path) and not file.startswith(job_id):
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
                    return {
                        "job_id": job_id,
                        "format_type": "audio"
                    }
        
        raise Exception("Downloaded file not found")
        
    except Exception as e:
        if os.path.exists(temp_path):
            cleanup_file(temp_path)
        
        error_msg = str(e)
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(400, "Authentication required. Please extract cookies from your browser.")
        
        raise HTTPException(500, f"Download failed: {error_msg[:200]}")

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
        if video_path and os.path.exists(video_path): 
            cleanup_file(video_path)
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
