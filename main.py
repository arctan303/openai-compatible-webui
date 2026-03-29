import json
import os
import base64
import mimetypes
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import FastAPI, Request, Response, Depends, HTTPException, UploadFile, File, Form, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
from auth import create_access_token, decode_token
from config import MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await database.get_user_by_id(int(payload.get("sub")))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user=Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ─────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token = request.cookies.get("access_token")
    if token and decode_token(token):
        return templates.TemplateResponse("chat.html", {"request": request})
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/")
    payload = decode_token(token)
    if not payload:
        return RedirectResponse(url="/")
    user = await database.get_user_by_id(int(payload.get("sub")))
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/chat")
    return templates.TemplateResponse("admin.html", {"request": request})


# ─────────────────────────────────────────────
# Auth API
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    user = await database.get_user_by_username(body.username)
    if not user or not database.verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": str(user["id"])})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return {
        "ok": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "model": user["model"],
            "is_admin": bool(user["is_admin"])
        }
    }


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    import json as _json
    allowed = None
    if user.get("allowed_models"):
        try:
            allowed = _json.loads(user["allowed_models"])
        except Exception:
            allowed = None
    return {
        "id": user["id"],
        "username": user["username"],
        "model": user["model"],
        "api_base": user["api_base"],
        "allowed_models": allowed,
        "is_admin": bool(user["is_admin"])
    }


# ─────────────────────────────────────────────
# Chat streaming proxy
# ─────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: object  # str or list (for vision)


class ChatRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, user=Depends(get_current_user)):
    admin_cfg = await database.get_admin_config()
    if not admin_cfg:
        raise HTTPException(status_code=500, detail="系统未配置管理员")

    api_base = admin_cfg["api_base"].rstrip("/")
    api_key = user["api_key"] if user["api_key"] else admin_cfg["api_key"]
    model = body.model or user["model"]

    # Validate model against allowed_models whitelist
    if user.get("allowed_models"):
        try:
            allowed = json.loads(user["allowed_models"])
            if allowed and model not in allowed:
                model = allowed[0]  # fallback to first allowed model
        except Exception:
            pass

    payload = {
        "model": model,
        "messages": [m.model_dump() for m in body.messages],
        "stream": True,
        "temperature": body.temperature,
    }
    if body.max_tokens:
        payload["max_tokens"] = body.max_tokens

    async def generate():
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{api_base}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                if resp.status_code != 200:
                    body_text = await resp.aread()
                    yield f"data: {json.dumps({'error': body_text.decode()})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if line:
                        yield f"{line}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─────────────────────────────────────────────
# Models list
# ─────────────────────────────────────────────

@app.get("/api/models")
async def get_models(user=Depends(get_current_user)):
    """Fetch model list from user's API base, filtered by allowed_models whitelist."""
    admin_cfg = await database.get_admin_config()
    if not admin_cfg:
        raise HTTPException(status_code=500, detail="系统未配置管理员")
        
    api_base = admin_cfg["api_base"].rstrip("/")
    api_key = user["api_key"] if user["api_key"] else admin_cfg["api_key"]
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            models = sorted(data.get("data", []), key=lambda m: m.get("id", ""))

            # Filter by allowed_models whitelist if set
            if user.get("allowed_models"):
                try:
                    allowed = json.loads(user["allowed_models"])
                    if allowed:
                        models = [m for m in models if m["id"] in allowed]
                except Exception:
                    pass

            return {"data": models}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@app.get("/api/admin/models")
async def get_admin_models(api_base: str = "", api_key: str = "", admin=Depends(require_admin)):
    """Admin: fetch ALL models from any API base (for building user model whitelist)."""
    admin_cfg = await database.get_admin_config()
    if not admin_cfg:
        raise HTTPException(status_code=500, detail="系统未配置管理员")
        
    actual_base = (api_base or admin_cfg["api_base"]).rstrip("/")
    actual_key = api_key if api_key and '*' not in api_key else admin_cfg["api_key"]
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{actual_base}/models",
                headers={"Authorization": f"Bearer {actual_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            models = sorted(data.get("data", []), key=lambda m: m.get("id", ""))
            return {"data": models}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


# ─────────────────────────────────────────────
# File upload
# ─────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件过大（最大 10MB）")

    mime = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    is_image = mime.startswith("image/")

    if is_image:
        b64 = base64.b64encode(content).decode()
        return {
            "type": "image",
            "name": file.filename,
            "mime": mime,
            "data": f"data:{mime};base64,{b64}",
        }
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        return {
            "type": "text",
            "name": file.filename,
            "content": text,
        }


# ─────────────────────────────────────────────
# Admin API
# ─────────────────────────────────────────────

@app.get("/api/admin/users")
async def list_users(admin=Depends(require_admin)):
    users = await database.get_all_users()
    for u in users:
        key = u.get("api_key", "")
        if key:
            if len(key) > 8:
                u["api_key"] = key[:3] + "*" * 6 + key[-4:]
            else:
                u["api_key"] = "********"
    return users


class CreateUserRequest(BaseModel):
    username: str
    password: str
    api_key: str = ""
    api_base: str = ""
    model: str = "gpt-4o"
    is_admin: int = 0
    allowed_models: Optional[List[str]] = None


@app.post("/api/admin/users")
async def create_user_route(body: CreateUserRequest, admin=Depends(require_admin)):
    try:
        allowed_json = json.dumps(body.allowed_models) if body.allowed_models is not None else None
        await database.create_user(
            body.username, body.password, body.api_key,
            body.api_base, body.model, body.is_admin, allowed_json
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")


class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: Optional[str] = None
    is_admin: Optional[int] = None
    allowed_models: Optional[List[str]] = None  # None = unchanged, [] = all allowed


@app.put("/api/admin/users/{user_id}")
async def update_user_route(user_id: int, body: UpdateUserRequest, admin=Depends(require_admin)):
    raw = body.model_dump()
    data = {}
    for k, v in raw.items():
        if k == "allowed_models":
            # Explicitly serialize: empty list = all allowed (NULL), list = JSON
            if v is not None:
                data["allowed_models"] = json.dumps(v) if v else None
        elif k == "password":
            if v:  # Only update password if not empty
                data["password"] = v
        elif k == "api_key":
            if v and "*" in v:
                pass  # Ignore masked string
            else:
                data["api_key"] = v if v is not None else ""
        elif k == "api_base":
            pass  # Ignore api_base completely as it is centrally managed
        elif v is not None:
            data[k] = v
    if data:
        await database.update_user(user_id, data)
    return {"ok": True}


@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: int, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    await database.delete_user(user_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
