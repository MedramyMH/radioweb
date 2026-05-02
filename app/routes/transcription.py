import os, uuid, asyncio
from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services.transcription_service import transcribe_audio
import yt_dlp

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def cleanup_file(path: str):
    if os.path.exists(path):
        try: os.remove(path)
        except: pass

@router.get("/transcription", response_class=HTMLResponse)
async def transcription_page(request: Request):
    return templates.TemplateResponse("transcription.html", {"request": request})

@router.post("/api/transcribe")
async def api_transcribe(
    request: Request, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(None), 
    url: str = Form(None), 
    language: str = Form("en")
):
    temp_path = None
    
    try:
        # If URL is provided, download audio first using yt-dlp
        if url:
            file_id = str(uuid.uuid4())
            outtmpl = f"/tmp/{file_id}.%(ext)s"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': outtmpl,
                'quiet': True,
                'socket_timeout': 60,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                temp_path = f"/tmp/{file_id}.mp3"
                
        elif file:
            temp_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
            with open(temp_path, "wb") as buffer:
                buffer.write(await file.read())
        else:
            raise HTTPException(status_code=400, detail="Provide a file or URL")
            
        # Run Whisper
        segments = await asyncio.to_thread(transcribe_audio, temp_path, language)
        full_text = " ".join([s["text"] for s in segments])
        
        # Cleanup the downloaded/uploaded audio in the background
        background_tasks.add_task(cleanup_file, temp_path)
        
        return JSONResponse({"text": full_text, "segments": segments})
        
    except Exception as e:
        if temp_path and os.path.exists(temp_path): cleanup_file(temp_path)
        raise HTTPException(status_code=500, detail=str(e))