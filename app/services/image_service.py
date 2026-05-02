import io
import base64
from PIL import Image, ImageFilter, ImageOps

PRESETS = {
    "youtube_thumbnail": (1280, 720),
    "facebook_post": (1200, 630),
    "facebook_square": (1080, 1080),
    "tiktok_cover": (1080, 1920),
    "instagram_post": (1080, 1080),
    "instagram_story": (1080, 1920),
    "twitter_post": (1600, 900),
}

QUALITY_MAP = {
    "hd": 85,
    "fhd": 92,
    "uhd": 100,
}

def process_base64_image(base64_str: str, preset: str, custom_w: int, custom_h: int, quality: str, format: str) -> bytes:
    # Strip the "data:image/...;base64," prefix
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]
        
    img_bytes = base64.b64decode(base64_str)
    img = Image.open(io.BytesIO(img_bytes))

    if img.mode == "RGBA" and format == "JPEG":
        # Create white background for transparent images if saving as JPEG
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB" and img.mode != "RGBA":
        img = img.convert("RGB")

    # Determine Dimensions
    if preset and preset in PRESETS:
        target_w, target_h = PRESETS[preset]
    elif custom_w and custom_h:
        target_w, target_h = custom_w, custom_h
    else:
        target_w, target_h = img.size

    # Smart Resize & Crop
    img = ImageOps.fit(img, (target_w, target_h), method=Image.LANCZOS)
    
    # Sharpen slightly after resize
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=100))

    # Save
    output_buffer = io.BytesIO()
    save_quality = QUALITY_MAP.get(quality, 92)
    img.save(output_buffer, format=format, quality=save_quality, optimize=True)
    output_buffer.seek(0)
    
    return output_buffer.getvalue()