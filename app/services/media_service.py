import os, uuid, json
from pathlib import Path
import subprocess
import yt_dlp
import moviepy
try:
    from moviepy.editor import VideoFileClip, AudioFileClip
except (ImportError, AttributeError):
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
        from moviepy.audio.io.AudioFileClip import AudioFileClip
    except ImportError:
        from moviepy import VideoFileClip, AudioFileClip


TEMP_DIR = Path("/tmp/media")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def download_media(url: str, format_type: str) -> dict:
    file_id = str(uuid.uuid4())
    outtmpl = str(TEMP_DIR / f"{file_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': outtmpl,
        'quiet': True,
        'socket_timeout': 120,
        'retries': 10,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    if format_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        if format_type == 'mp3': filepath = str(TEMP_DIR / f"{file_id}.mp3")
        return {"title": info.get('title'), "filepath": filepath}

def get_video_metadata(video_path: str, job_id: str) -> dict:
    """Gets duration and creates a thumbnail using FFmpeg directly (faster than moviepy)"""
    thumb_path = str(TEMP_DIR / f"{job_id}.jpg")
    
    # Get duration
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    duration = float(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
    
    # Get thumbnail at 1 second
    subprocess.run(['ffmpeg', '-i', video_path, '-ss', '00:00:01.000', '-vframes', '1', '-q:v', '2', thumb_path, '-y'], capture_output=True)
    
    return {"duration": duration, "thumbnail": f"/tmp/media/{job_id}.jpg"}

def process_editor_actions(video_path: str, start: float, end: float, volume: float, speed: float) -> str:
    output_path = str(TEMP_DIR / f"out_{uuid.uuid4()}.mp4")
    
    clip = VideoFileClip(video_path)
    
    # Trim
    if end and end > start:
        clip = clip.subclip(start, end)
    elif start > 0:
        clip = clip.subclip(start, clip.duration)

    # Speed
    if speed != 1.0:
        clip = clip.fx(lambda c, s=speed: c.speedx(s))

    # Volume
    if volume != 1.0:
        clip = clip.volumex(volume)

    clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    return output_path
