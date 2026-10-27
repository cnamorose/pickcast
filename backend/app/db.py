import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

# 로컬에서는 프로젝트 루트 .env를 읽는다.
# 배포 환경에서는 플랫폼이 넣어준 환경변수가 우선한다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL이 없습니다. 프로젝트 루트에서 .env.example을 .env로 복사하고 값을 채우세요."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_tables():
    # 없는 테이블만 만든다. 기존 테이블과 데이터는 건드리지 않는다.
    SQLModel.metadata.create_all(engine)


def get_db():
    with Session(engine) as db:
        yield db
