import base64
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import NewsArticle
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

async def admin_guard(request: Request):
    user = await get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/auth/login", status_code=303)
    return user

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse): return user
    
    articles = []
    try:
        stmt = select(NewsArticle).order_by(NewsArticle.created_at.desc()).limit(50)
        result = await db.execute(stmt)
        articles = result.scalars().all()
    except Exception as e:
        print(f"[ADMIN FETCH ERROR]: {e}")
        
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, "user": user, "articles": articles
    })

@router.post("/create")
async def create_news(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    title: str = Form(...),
    content: str = Form(""),
    category: str = Form(...),
    meta_description: str = Form(None),
    is_featured: bool = Form(False),
    image: UploadFile = File(None)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse): return user
    
    image_url = None
    try:
        # Handle Cover Image Upload
        if image and image.filename:
            contents = await image.read()
            # Convert image to Base64 so it saves directly in the DB image_url column
            image_url = f"data:image/jpeg;base64,{base64.b64encode(contents).decode('utf-8')}"
            
        article = NewsArticle(
            title=title,
            content=content,
            category=category,
            image_url=image_url,
            is_featured=is_featured,
            meta_description=meta_description
        )
        db.add(article)
        await db.commit()
        print("[ADMIN SUCCESS] Article saved to database!")
    except Exception as e:
        await db.rollback()
        print(f"[ADMIN SAVE ERROR]: {e}") # Look at your terminal for this message!
        
    return RedirectResponse("/admin/", status_code=303)

@router.post("/delete/{article_id}")
async def delete_news(article_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse): return user
    
    try:
        stmt = select(NewsArticle).where(NewsArticle.id == article_id)
        result = await db.execute(stmt)
        article = result.scalar_one_or_none()
        if article:
            await db.delete(article)
            await db.commit()
    except Exception as e:
        print(f"[ADMIN DELETE ERROR]: {e}")
        
    return RedirectResponse("/admin/", status_code=303)