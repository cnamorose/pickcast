from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  테이블 정의를 등록
from .dashboard_api import router as dashboard_router
from .db import create_tables, engine
from .sessions import router as sessions_router


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

create_tables()

app.include_router(sessions_router)
app.include_router(dashboard_router)


@app.get("/")
def root():
    return {
        "message": "PickCast Backend is running"
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as error:
        db_status = f"error: {error.__class__.__name__}"

    return {
        "status": "ok",
        "ml_model": "loaded",
        "db": db_status,
    }