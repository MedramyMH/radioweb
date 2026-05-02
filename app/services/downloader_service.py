import yt_dlp

def process_download(url: str, save_path: str = "downloads/"):
    ydl_opts = {
        'outtmpl': f'{save_path}%(id)s.%(ext)s',
        'format': 'bestaudio/best' if 'mp3' in url.lower() else 'bestvideo+bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if 'mp3' in url.lower() else [],
        'quiet': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            # In production, use BackgroundTasks or Celery to run ydl.download(url) here
            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "formats": [{"format": f["format"], "ext": f["ext"]} for f in info.get("formats", [])[:5]]
            }
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")