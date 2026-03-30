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
import setup_wizard
from auth import create_access_token, decode_token
from config import (
    MAX_UPLOAD_SIZE,
    ALLOWED_EXTENSIONS,
    SECRET_KEY,
    DATABASE_URL,
    BOOTSTRAP_ADMIN_USERNAME,
    BOOTSTRAP_SYSTEM_API_BASE,
    BOOTSTRAP_SYSTEM_MODEL,
    SETUP_WIZARD_ENABLED,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SECRET_KEY == "change-this-secret-key-in-production-please":
        print("\u26a0️  WARNING: SECRET_KEY is using the insecure default value. Set a strong SECRET_KEY in your .env file!")
    await database.init_db()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def parse_model_aliases(raw_value) -> dict:
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return {str(k): str(v) for k, v in raw_value.items() if str(k).strip() and str(v).strip()}
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if str(k).strip() and str(v).strip()}


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


@app.get("/chat/{conv_id}", response_class=HTMLResponse)
async def chat_page_with_conversation(conv_id: str, request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("chat.html", {"request": request, "conv_id": conv_id})


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


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if not SETUP_WIZARD_ENABLED:
        return RedirectResponse(url="/admin")
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/")
    payload = decode_token(token)
    if not payload:
        return RedirectResponse(url="/")
    user = await database.get_user_by_id(int(payload.get("sub")))
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/chat")

    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "database_url": DATABASE_URL,
            "admin_username": BOOTSTRAP_ADMIN_USERNAME,
            "system_api_base": BOOTSTRAP_SYSTEM_API_BASE,
            "system_model": BOOTSTRAP_SYSTEM_MODEL,
        },
    )


# ─────────────────────────────────────────────
# Auth API
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class SetupInitializeRequest(BaseModel):
    database_url: str
    admin_username: str
    admin_password: str
    system_api_base: str
    system_api_key: str = ""
    system_model: str = "gpt-4o"


@app.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    user = await database.get_user_by_username(body.username)
    if not user or not database.verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": str(user["id"])})
    is_production = os.environ.get("ENV", "development") == "production"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_production,
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


@app.get("/api/setup/status")
async def setup_status(admin=Depends(require_admin)):
    if not SETUP_WIZARD_ENABLED:
        raise HTTPException(status_code=403, detail="初始化向导已关闭，请改 .env 后重启服务")
    return {
        "database_url": DATABASE_URL,
        "is_postgres": setup_wizard.is_postgres_url(DATABASE_URL),
        "using_default_sqlite": DATABASE_URL == "sqlite:///data/chat.db",
        "setup_wizard_enabled": SETUP_WIZARD_ENABLED,
    }


@app.post("/api/setup/initialize")
async def setup_initialize(body: SetupInitializeRequest, admin=Depends(require_admin)):
    if not SETUP_WIZARD_ENABLED:
        raise HTTPException(status_code=403, detail="初始化向导已关闭，请改 .env 后重启服务")

    database_url = body.database_url.strip()
    admin_username = body.admin_username.strip()
    admin_password = body.admin_password
    system_api_base = body.system_api_base.strip()
    system_api_key = body.system_api_key.strip()
    system_model = body.system_model.strip() or "gpt-4o"

    if not database_url:
        raise HTTPException(status_code=400, detail="数据库连接不能为空")
    if not admin_username:
        raise HTTPException(status_code=400, detail="管理员用户名不能为空")
    if not admin_password:
        raise HTTPException(status_code=400, detail="管理员密码不能为空")
    if not system_api_base:
        raise HTTPException(status_code=400, detail="System API Base 不能为空")

    try:
        await setup_wizard.initialize_database(
            database_url=database_url,
            admin_username=admin_username,
            admin_password=admin_password,
            system_api_base=system_api_base,
            system_api_key=system_api_key,
            system_model=system_model,
        )
        setup_wizard.write_env_file(
            database_url=database_url,
            admin_username=admin_username,
            admin_password=admin_password,
            system_api_base=system_api_base,
            system_api_key=system_api_key,
            system_model=system_model,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"初始化失败: {str(e)}")

    return {
        "ok": True,
        "restart_required": database_url != DATABASE_URL,
        "message": "初始化完成",
    }


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    system_cfg = await database.get_system_config()
    model_aliases = parse_model_aliases(system_cfg.get("model_aliases") if system_cfg else None)
    allowed = None
    if user.get("allowed_models"):
        try:
            allowed = json.loads(user["allowed_models"])
        except Exception:
            allowed = None
    return {
        "id": user["id"],
        "username": user["username"],
        "model": user["model"],
        "api_base": system_cfg["api_base"] if system_cfg else "",
        "system_default_model": system_cfg["default_model"] if system_cfg else "gpt-4o",
        "model_aliases": model_aliases,
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
    system_cfg = await database.get_system_config()
    if not system_cfg:
        raise HTTPException(status_code=500, detail="系统未配置")

    api_base = system_cfg["api_base"].rstrip("/")
    api_key = user["api_key"] if user["api_key"] else system_cfg["api_key"]
    model = body.model or user["model"] or system_cfg["default_model"]

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
# AI Title Generation
# ─────────────────────────────────────────────

class GenerateTitleRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None


@app.post("/api/history/{conv_id}/generate_title")
async def generate_title(conv_id: str, body: GenerateTitleRequest, user=Depends(get_current_user)):
    system_cfg = await database.get_system_config()
    if not system_cfg:
        raise HTTPException(status_code=500, detail="系统未配置")

    api_base = system_cfg["api_base"].rstrip("/")
    api_key = user["api_key"] if user["api_key"] else system_cfg["api_key"]
    model = body.model or user["model"] or system_cfg["default_model"]

    # Simple prompt for title generation
    messages = [
        {"role": "system", "content": "你是一个标题生成助手。请根据用户提供的对话片段，生成一个极其简短、有吸引力且准确的对话标题（不超过10个字）。直接返回标题文本，不要包含引号或任何解释。"},
    ]
    # Only take first few messages to save tokens and context
    messages.extend([m.model_dump() for m in body.messages[:2]])
    messages.append({"role": "user", "content": "请为以上对话生成一个简减短的标题。"})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 50,
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            title = data["choices"][0]["message"]["content"].strip().strip('"').strip('《》')
            
            # Update database
            conv = await database.get_conversations(user["id"])
            target = next((c for c in conv if c["id"] == conv_id), None)
            if target:
                await database.save_conversation(conv_id, user["id"], title, target["messages"], target["model"])
            
            return {"title": title}
    except Exception as e:
        print(f"Title generation failed: {e}")
        return {"title": None}


# ─────────────────────────────────────────────
# Models list
# ─────────────────────────────────────────────

@app.get("/api/models")
async def get_models(user=Depends(get_current_user)):
    """Fetch model list from user's API base, filtered by allowed_models whitelist."""
    system_cfg = await database.get_system_config()
    if not system_cfg:
        raise HTTPException(status_code=500, detail="系统未配置")
    model_aliases = parse_model_aliases(system_cfg.get("model_aliases"))
        
    api_base = system_cfg["api_base"].rstrip("/")
    api_key = user["api_key"] if user["api_key"] else system_cfg["api_key"]
    
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

            for model in models:
                model["display_name"] = model_aliases.get(model["id"], model["id"])

            return {"data": models}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"API 错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@app.get("/api/admin/models")
async def get_admin_models(api_base: str = "", api_key: str = "", admin=Depends(require_admin)):
    """Admin: fetch ALL models from any API base (for building user model whitelist)."""
    system_cfg = await database.get_system_config()
    if not system_cfg:
        raise HTTPException(status_code=500, detail="系统未配置")
        
    actual_base = (api_base or system_cfg["api_base"]).rstrip("/")
    actual_key = api_key if api_key and '*' not in api_key else system_cfg["api_key"]
    
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

class SystemConfigRequest(BaseModel):
    api_base: str
    api_key: str = ""
    default_model: str = "gpt-4o"
    model_aliases: Optional[dict] = None


@app.get("/api/admin/system")
async def get_admin_system(admin=Depends(require_admin)):
    system_cfg = await database.get_system_config()
    if not system_cfg:
        raise HTTPException(status_code=500, detail="系统未配置")

    masked_key = system_cfg["api_key"] or ""
    if masked_key:
        masked_key = masked_key[:3] + "*" * 6 + masked_key[-4:] if len(masked_key) > 8 else "********"

    return {
        "api_base": system_cfg["api_base"],
        "api_key": masked_key,
        "default_model": system_cfg["default_model"],
        "model_aliases": parse_model_aliases(system_cfg.get("model_aliases")),
    }


@app.put("/api/admin/system")
async def update_admin_system(body: SystemConfigRequest, admin=Depends(require_admin)):
    data = {
        "api_base": body.api_base.strip(),
        "default_model": body.default_model.strip() or "gpt-4o",
        "model_aliases": json.dumps(parse_model_aliases(body.model_aliases)),
    }
    if body.api_key and "*" in body.api_key:
        pass
    else:
        data["api_key"] = body.api_key.strip()

    if not data["api_base"]:
        raise HTTPException(status_code=400, detail="API Base 不能为空")

    await database.update_system_config(data)
    return {"ok": True}


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
    model: str = "gpt-4o"
    is_admin: int = 0
    allowed_models: Optional[List[str]] = None


@app.post("/api/admin/users")
async def create_user_route(body: CreateUserRequest, admin=Depends(require_admin)):
    try:
        allowed_json = json.dumps(body.allowed_models) if body.allowed_models is not None else None
        await database.create_user(
            body.username, body.password, body.api_key,
            body.model, body.is_admin, allowed_json
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")


class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    api_key: Optional[str] = None
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


# ─────────────────────────────────────────────
# Chat History Sync API
# ─────────────────────────────────────────────

class SaveHistoryRequest(BaseModel):
    title: str
    messages: list
    model: str


@app.get("/api/history")
async def get_history(user=Depends(get_current_user)):
    conversations = await database.get_conversations(user["id"])
    return conversations


@app.post("/api/history/{conv_id}")
async def save_history(conv_id: str, body: SaveHistoryRequest, user=Depends(get_current_user)):
    await database.save_conversation(conv_id, user["id"], body.title, body.messages, body.model)
    return {"ok": True}


@app.delete("/api/history/{conv_id}")
async def delete_history_route(conv_id: str, user=Depends(get_current_user)):
    await database.delete_conversation(conv_id, user["id"])
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
