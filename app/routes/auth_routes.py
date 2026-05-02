from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import create_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "type": "login"})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "type": "register"})

@router.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    # ==========================================
    # 1. HARDCODED ADMIN BYPASS (NO DATABASE)
    # ==========================================
    if username == "admin" and password == "admin12345*-":
        token = create_token({
            "user_id": 0, 
            "username": "Admin", 
            "is_admin": True
        })
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("access_token", token, httponly=True, max_age=86400)
        return resp

    # ==========================================
    # 2. NORMAL USER DATABASE LOGIN (OPTIONAL)
    # ==========================================
    try:
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select
        from app.database import get_db
        from app.models import User
        from app.auth import verify_password
        
        # Safely try database login
        async for db in get_db():
            stmt = select(User).where(User.username == username)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user and verify_password(password, user.hashed_password):
                token = create_token({"user_id": user.id, "username": user.username, "is_admin": user.is_admin})
                resp = RedirectResponse("/", status_code=303)
                resp.set_cookie("access_token", token, httponly=True, max_age=86400)
                return resp
            break 
            
    except Exception as e:
        print(f"[AUTH ERROR] Database login failed: {e}")

    # ==========================================
    # 3. LOGIN FAILED
    # ==========================================
    return templates.TemplateResponse("login.html", {
        "request": request, "type": "login", 
        "error": "Invalid username or password",
        "username": username
    })

@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    response.body = b"<html><head><script>window.location.href='/';</script></head></html>"
    return response