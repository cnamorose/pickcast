from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  테이블 정의를 등록
from .dashboard_api import router as dashboard_router
from .db import create_tables, engine
from .ml import get_predictor, models
from .peak_api import router as peak_router
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
app.include_router(peak_router)


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
        # 지금 쓰는 모델 버전. current.json을 바꾸면 몇 초 안에 따라 바뀐다.
        "model_version": get_predictor().version,
        # 새 버전을 불러오다 실패해 이전 버전을 계속 쓰는 경우 그 이유
        "model_error": models.last_error,
        "db": db_status,
    }