import yt_dlp
from typing import Dict, List, Optional
import os

def get_youtube_cookies_path():
    """Try to get cookies from common browser locations"""
    cookie_paths = [
        os.path.expanduser("~/.config/yt-dlp/cookies.txt"),
        os.path.expanduser("~/yt-dlp-cookies.txt"),
        "/tmp/youtube_cookies.txt",
    ]
    
    for path in cookie_paths:
        if os.path.exists(path):
            return path
    return None

def get_available_formats(url: str, cookies_path: str = None) -> Dict:
    """
    Extract available video/audio formats without downloading.
    Returns metadata and list of available qualities.
    
    Handles YouTube authentication by:
    1. Using browser cookies if available
    2. Adding realistic user-agent headers
    3. Using alternative extractors
    """
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        # Add browser-like headers
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
    }
    
    # Add cookies if available
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    
    # Try with default options first
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return _process_formats(info)
    except Exception as e:
        error_str = str(e)
        
        # If it's a YouTube bot detection error, try alternative approach
        if 'Sign in to confirm' in error_str or 'bot' in error_str.lower():
            # Try with extract_flat and format fallback
            try:
                ydl_opts['extract_flat'] = 'in_playlist'
                ydl_opts['skip_download'] = True
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return _process_formats(info)
            except:
                pass
            
            # Last resort: return generic formats
            return {
                "title": "Video (Authentication Required)",
                "thumbnail": "",
                "duration": 0,
                "uploader": "Unknown",
                "video_formats": [
                    {
                        'format_id': '18',
                        'quality': '360p (Default)',
                        'height': 360,
                        'fps': 30,
                        'ext': 'mp4',
                        'filesize_mb': 0,
                        'vcodec': 'h264',
                        'note': 'Requires authentication'
                    }
                ],
                "audio_formats": [
                    {
                        'format_id': '251',
                        'quality': '128kbps (Default)',
                        'bitrate': 128,
                        'ext': 'm4a',
                        'filesize_mb': 0,
                        'acodec': 'opus',
                        'note': 'Requires authentication'
                    }
                ],
                "auth_required": True,
                "auth_message": "YouTube requires authentication. Please extract and provide cookies."
            }
        
        # For other errors, provide helpful message
        raise Exception(f"Failed to fetch video info: {error_str}")


def _process_formats(info: Dict) -> Dict:
    """Process extracted info into format options"""
    
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
        "video_formats": unique_video[:15],  # Top 15 qualities
        "audio_formats": unique_audio[:10],   # Top 10 qualities
        "auth_required": False,
    }


def download_media(url: str, format_id: str, save_path: str = "downloads/", cookies_path: str = None) -> Dict:
    """
    Download media with the specified format_id.
    format_id should be provided from get_available_formats.
    """
    ydl_opts = {
        'format': format_id,
        'outtmpl': f'{save_path}%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        # Add browser-like headers
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'socket_timeout': 30,
    }
    
    # Add cookies if available
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return {
                "success": True,
                "message": "Download completed"
            }
    except Exception as e:
        error_str = str(e)
        
        # Handle authentication errors with helpful message
        if 'Sign in to confirm' in error_str or 'bot' in error_str.lower():
            raise Exception(
                "YouTube authentication required. "
                "Please see the FAQ section in the app for how to extract and provide cookies."
            )
        
        raise Exception(f"Download failed: {error_str}")


def extract_cookies_from_browser(browser: str = "chrome") -> str:
    """
    Extract cookies from browser.
    Supported browsers: chrome, firefox, edge, safari
    
    Returns path to cookies file
    """
    try:
        import browser_cookie3
        
        # Get cookies
        if browser.lower() == "chrome":
            cj = browser_cookie3.chrome()
        elif browser.lower() == "firefox":
            cj = browser_cookie3.firefox()
        elif browser.lower() == "edge":
            cj = browser_cookie3.edge()
        else:
            return None
        
        # Save to file
        cookies_path = os.path.expanduser("~/yt-dlp-cookies.txt")
        
        # Convert to Netscape format (yt-dlp compatible)
        with open(cookies_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in cj:
                if cookie.domain == '.youtube.com' or 'youtube' in cookie.domain:
                    line = f"{cookie.domain}\tTRUE\t{cookie.path}\t{str(cookie.secure).upper()}\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n"
                    f.write(line)
        
        return cookies_path
    
    except ImportError:
        return None
