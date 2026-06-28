import io
import base64
import httpx
from fastapi import APIRouter, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services.image_service import process_base64_image

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ── Lazy rembg session (loads model on first request) ──────────────────
_rembg_session = None

def _get_rembg_session():
    global _rembg_session
    if _rembg_session is None:
        try:
            from rembg import new_session
            _rembg_session = new_session("u2net")
        except Exception as e:
            raise RuntimeError(f"Could not load rembg model: {e}")
    return _rembg_session

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

@router.get("/image-tools", response_class=HTMLResponse)
async def image_tools_page(request: Request):
    return templates.TemplateResponse("tools_image.html", {"request": request})


@router.post("/api/image/remove-bg")
async def remove_background(
    file: UploadFile = File(...),
    model: str = Form("u2net"),
    alpha_matting: bool = Form(True)
):
    try:
        from rembg import remove, new_session
        from PIL import Image

        contents = await file.read()
        input_img = Image.open(io.BytesIO(contents)).convert("RGBA")

        session = new_session(model)

        output_img = remove(
            input_img,
            session=session,
            alpha_matting=alpha_matting,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10
        )

        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        buf.seek(0)

        b64 = base64.b64encode(buf.read()).decode()
        return {"base64": f"data:image/png;base64,{b64}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/api/image/magic-remove")
async def magic_remove(
    image: UploadFile = File(...),
    mask: UploadFile = File(...)
):
    from PIL import Image

    img = Image.open(io.BytesIO(await image.read())).convert("RGBA")
    msk = Image.open(io.BytesIO(await mask.read())).convert("L")

    # Invert mask → white = remove
    msk = msk.point(lambda p: 255 - p)

    img.putalpha(msk)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    b64 = base64.b64encode(buf.read()).decode()
    return {"base64": f"data:image/png;base64,{b64}"}