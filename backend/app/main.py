from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from . import models  # noqa: F401  테이블 정의를 등록
from .db import create_tables, engine
from .ml import FEATURE_LABELS, predictor
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


class ViewEvent(BaseModel):
    timestamp: int
    item_id: str


class PredictRequest(BaseModel):
    views: list[ViewEvent]


@app.post("/predictions")
def predict(request: PredictRequest):
    views = [
        (event.timestamp, event.item_id)
        for event in request.views
    ]

    return {
        "prediction": predictor.predict(views),
        "timeline": predictor.timeline(views),
        "feature_labels": FEATURE_LABELS,
    }