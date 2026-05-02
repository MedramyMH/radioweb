import io
import base64
import httpx
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from app.services.image_service import process_base64_image

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/image-tools", response_class=HTMLResponse)
async def image_tools_page(request: Request):
    return templates.TemplateResponse("tools_image.html", {"request": request})

# NEW: Safe URL Proxy to bypass CORS
@router.get("/api/image/fetch-url")
async def fetch_image_url(url: str):
    try:
        # Download image securely on the backend
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        
        # Convert to base64 safely
        b64 = base64.b64encode(response.content).decode("utf-8")
        
        # Guess mime type
        content_type = response.headers.get("content-type", "image/jpeg")
        if "png" in content_type:
            mime = "image/png"
        else:
            mime = "image/jpeg"
            
        return {"base64": f"data:{mime};base64,{b64}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not download image: {str(e)}")

@router.post("/api/image/process")
async def api_process_image(
    image_b64: str = Form(...),
    preset: str = Form(None),
    custom_w: int = Form(None),
    custom_h: int = Form(None),
    quality: str = Form("fhd"),
    format: str = Form("JPEG")
):
    try:
        processed_bytes = process_base64_image(
            base64_str=image_b64,
            preset=preset,
            custom_w=custom_w,
            custom_h=custom_h,
            quality=quality,
            format=format
        )
        
        ext = "jpg" if format == "JPEG" else "png"
        mime_type = "image/jpeg" if format == "JPEG" else "image/png"
        filename = f"processed_{preset or 'custom'}.{ext}"
        
        return Response(
            content=processed_bytes, 
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))