from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import os
import uuid
import aiofiles

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
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse):
        return user

    stmt = select(NewsArticle).order_by(
        NewsArticle.created_at.desc()
    ).limit(50)

    result = await db.execute(stmt)

    return templates.TemplateResponse(request,
        "admin_dashboard.html",
        {
            "request": request,
            "user": user,
            "articles": result.scalars().all()
        }
    )


@router.post("/create")
async def create_news(
    request: Request,
    db: AsyncSession = Depends(get_db),
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form(...),
    meta_description: str = Form(None),
    is_featured: bool = Form(False),
    image: UploadFile = File(None)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse):
        return user

    image_url = None

    if image and image.filename:

        os.makedirs("app/static/uploads", exist_ok=True)

        ext = image.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{ext}"

        filepath = f"app/static/uploads/{filename}"

        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await image.read())

        image_url = f"/static/uploads/{filename}"

    article = NewsArticle(
        title=title,
        content=content,
        category=category,
        image_url=image_url,
        meta_description=meta_description,
        is_featured=is_featured
    )

    db.add(article)
    await db.commit()

    return RedirectResponse("/admin/", status_code=303)


# ----------------------------
# EDIT PAGE
# ----------------------------

@router.get("/edit/{article_id}", response_class=HTMLResponse)
async def edit_article(
    article_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(NewsArticle).where(
            NewsArticle.id == article_id
        )
    )

    article = result.scalar_one_or_none()

    if not article:
        return RedirectResponse("/admin/", status_code=303)

    return templates.TemplateResponse(request,
        "edit_article.html",
        {
            "request": request,
            "user": user,
            "article": article
        }
    )


# ----------------------------
# UPDATE ARTICLE
# ----------------------------

@router.post("/edit/{article_id}")
async def update_article(
    article_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form(...),
    meta_description: str = Form(None),
    is_featured: bool = Form(False),
    image: UploadFile = File(None)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(NewsArticle).where(
            NewsArticle.id == article_id
        )
    )

    article = result.scalar_one_or_none()

    if not article:
        return RedirectResponse("/admin/", status_code=303)

    article.title = title
    article.content = content
    article.category = category
    article.meta_description = meta_description
    article.is_featured = is_featured

    if image and image.filename:

        os.makedirs("app/static/uploads", exist_ok=True)

        ext = image.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{ext}"

        filepath = f"app/static/uploads/{filename}"

        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await image.read())

        article.image_url = f"/static/uploads/{filename}"

    await db.commit()

    return RedirectResponse("/admin/", status_code=303)


@router.post("/delete/{article_id}")
async def delete_news(
    article_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user = await admin_guard(request)
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(NewsArticle).where(
            NewsArticle.id == article_id
        )
    )

    article = result.scalar_one_or_none()

    if article:
        await db.delete(article)
        await db.commit()

    return RedirectResponse("/admin/", status_code=303)
