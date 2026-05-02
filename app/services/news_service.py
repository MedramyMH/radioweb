from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import NewsArticle, User
from ..auth import get_admin_user
from ..schemas import NewsCreate
from typing import List

router = APIRouter()

@router.get("/", response_model=List[NewsCreate])
def get_news(skip: int = 0, limit: int = 10, category: str = None, db: Session = Depends(get_db)):
    query = db.query(NewsArticle)
    if category: query = query.filter(NewsArticle.category == category)
    return query.order_by(NewsArticle.created_at.desc()).offset(skip).limit(limit).all()

@router.get("/trending", response_model=List[NewsCreate])
def get_trending(db: Session = Depends(get_db)):
    return db.query(NewsArticle).filter(NewsArticle.is_trending == True).limit(5).all()

@router.post("/")
def create_news(news: NewsCreate, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    db_news = NewsArticle(**news.dict())
    db.add(db_news); db.commit(); db.refresh(db_news)
    return db_news

@router.delete("/{news_id}")
def delete_news(news_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    db.query(NewsArticle).filter(NewsArticle.id == news_id).delete()
    db.commit()
    return {"status": "deleted"}