from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db
from app.models import RadioFavorite
from app.services import radio_service
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/radio", response_class=HTMLResponse)
async def radio_page(request: Request, q: str = None, show_favs: bool = False, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    
    if show_favs and user:
        stmt = select(RadioFavorite).where(RadioFavorite.user_id == user.get("id"))
        result = await db.execute(stmt)
        stations = [{"name": f.station_name, "url_resolved": f.stream_url, "favicon": "", "stationuuid": f.station_uuid} for f in result.scalars().all()]
    else:
        stations = await radio_service.search_radios(q) if q else await radio_service.get_tunisian_radios()
        
    return templates.TemplateResponse("radio.html", {
        "request": request, "stations": stations, "user": user, "show_favs": show_favs
    })

@router.post("/api/favorites/{action}")
async def toggle_favorite(action: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Login required"}, status_code=401)
    
    form = await request.form()
    user_id = user.get("id")
    
    if action == "add":
        stmt = select(RadioFavorite).where(RadioFavorite.user_id == user_id, RadioFavorite.station_uuid == form.get("uuid"))
        if not (await db.execute(stmt)).scalar_one_or_none():
            # REMOVED favicon= form.get("favicon") HERE
            db.add(RadioFavorite(user_id=user_id, station_uuid=form.get("uuid"), station_name=form.get("name"), stream_url=form.get("url")))
            await db.commit()
    elif action == "remove":
        await db.execute(delete(RadioFavorite).where(RadioFavorite.user_id == user_id, RadioFavorite.station_uuid == form.get("uuid")))
        await db.commit()
        
    return JSONResponse({"success": True})
