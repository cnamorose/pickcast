import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ml/product_purchase 폴더를 Python import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = PROJECT_ROOT / "ml" / "product_purchase"

sys.path.insert(0, str(ML_DIR))

from predict import FEATURE_LABELS, PurchasePredictor


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버가 시작될 때 ML 모델을 한 번만 로딩
predictor = PurchasePredictor()


@app.get("/")
def root():
    return {
        "message": "PickCast Backend is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ml_model": "loaded"
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