import yt_dlp
from typing import Dict, List, Optional

def get_available_formats(url: str) -> Dict:
    """
    Extract available video/audio formats without downloading.
    Returns metadata and list of available qualities.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract video formats
            video_formats = []
            audio_formats = []
            
            for fmt in info.get('formats', []):
                # Video with audio
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                    height = fmt.get('height', 0)
                    fps = fmt.get('fps', 30)
                    filesize = fmt.get('filesize', 0)
                    if height and height >= 240:  # Only include reasonable qualities
                        video_formats.append({
                            'format_id': fmt['format_id'],
                            'quality': f"{height}p",
                            'height': height,
                            'fps': fps,
                            'ext': fmt.get('ext', 'mp4'),
                            'filesize': filesize,
                            'filesize_mb': round(filesize / (1024*1024), 2) if filesize else 0,
                            'vcodec': fmt.get('vcodec', 'unknown'),
                        })
                
                # Audio only
                if fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
                    bitrate = fmt.get('abr', fmt.get('tbr', 128))
                    filesize = fmt.get('filesize', 0)
                    audio_formats.append({
                        'format_id': fmt['format_id'],
                        'quality': f"{bitrate}kbps",
                        'bitrate': bitrate,
                        'ext': fmt.get('ext', 'm4a'),
                        'filesize': filesize,
                        'filesize_mb': round(filesize / (1024*1024), 2) if filesize else 0,
                        'acodec': fmt.get('acodec', 'unknown'),
                    })
            
            # Sort by quality (highest first)
            video_formats.sort(key=lambda x: x['height'], reverse=True)
            audio_formats.sort(key=lambda x: x['bitrate'], reverse=True)
            
            # Remove duplicates (keep best for each quality level)
            seen_video = set()
            unique_video = []
            for fmt in video_formats:
                key = fmt['quality']
                if key not in seen_video:
                    seen_video.add(key)
                    unique_video.append(fmt)
            
            seen_audio = set()
            unique_audio = []
            for fmt in audio_formats:
                key = fmt['quality']
                if key not in seen_audio:
                    seen_audio.add(key)
                    unique_audio.append(fmt)
            
            return {
                "title": info.get('title', 'Unknown'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', ''),
                "video_formats": unique_video[:10],  # Top 10 qualities
                "audio_formats": unique_audio[:10],   # Top 10 qualities
            }
    except Exception as e:
        raise Exception(f"Failed to fetch video info: {str(e)}")


def download_media(url: str, format_id: str, save_path: str = "downloads/") -> Dict:
    """
    Download media with the specified format_id.
    format_id should be provided from get_available_formats.
    """
    ydl_opts = {
        'format': format_id,
        'outtmpl': f'{save_path}%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.download([url])
            return {
                "success": True,
                "message": "Download completed"
            }
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")
