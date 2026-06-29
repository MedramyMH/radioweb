from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import NewsArticle

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/news", response_class=HTMLResponse)
async def news_page(request: Request, category: str = None, page: int = 1, db: AsyncSession = Depends(get_db)):
    limit = 12
    offset = (page - 1) * limit
    stmt = select(NewsArticle).order_by(NewsArticle.id.desc()).offset(offset).limit(limit)
    
    if category:
        stmt = stmt.where(NewsArticle.category == category)
        
    result = await db.execute(stmt)
    articles = result.scalars().all()
    return templates.TemplateResponse(request, "news.html", {"articles": articles, "category": category})

@router.get("/news/{article_id}", response_class=HTMLResponse)
async def news_detail(article_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    # Fetch the main article
    stmt = select(NewsArticle).where(NewsArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()
    
    if not article:
        return RedirectResponse("/news")
        
    # Fetch Latest News (Last 5, excluding current)
    last_stmt = select(NewsArticle).where(NewsArticle.id != article_id).order_by(NewsArticle.id.desc()).limit(5)
    last_result = await db.execute(last_stmt)
    last_news = last_result.scalars().all()
    
    # Fetch Recommended News (Same category, excluding current. Fallback to latest if none)
    rec_stmt = select(NewsArticle).where(NewsArticle.id != article_id, NewsArticle.category == article.category).order_by(NewsArticle.id.desc()).limit(5)
    rec_result = await db.execute(rec_stmt)
    recommended = rec_result.scalars().all()
    
    if len(recommended) < 2:
        recommended = last_news # Fallback
        
    return templates.TemplateResponse(request, "news_detail.html", {
        "request": request, 
        "article": article, 
        "last_news": last_news, 
        "recommended": recommended
    })
