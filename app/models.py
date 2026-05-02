from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class NewsArticle(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(Text)
    category = Column(String)
    image_url = Column(String, nullable=True)
    is_featured = Column(Boolean, default=False)
    meta_description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RadioFavorite(Base):
    __tablename__ = "radio_favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    station_uuid = Column(String)
    station_name = Column(String)
    stream_url = Column(String)
    # REMOVED FAVICON - It's not in your SQL schema!