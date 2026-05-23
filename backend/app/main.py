from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.middleware import CSP, http_exception_handler
from app.config import settings
from db.session import engine
from db.init_data import init_database
from services.security_service import _init_semantic_detector
from api import auth, chat, knowledge, audit, config as config_api, security_tests

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        init_database(db)
        _init_semantic_detector()
    finally:
        db.close()
    yield
    # Shutdown


app = FastAPI(
    title="安全校园助手",
    description="具备提示注入防御、隐私保护与角色感知检索的智能校园助手系统",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS（开发环境宽松，生产环境收紧）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Exception handler
from fastapi.exceptions import HTTPException
app.add_exception_handler(HTTPException, http_exception_handler)

# API routers
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(config_api.router, prefix="/api")
app.include_router(security_tests.router, prefix="/api")

# Static files (frontend build output)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
