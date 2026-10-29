import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, SQLModel


def utc_now():
    return datetime.now(timezone.utc)


class ShoppingSession(SQLModel, table=True):
    """체험 한 번 = 세션 하나. 초기화하면 기록을 지우지 않고 새 세션을 만든다."""

    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    # experience: 체험 웹페이지 / simulated: 가상 손님 스크립트 / service: 실제 쇼핑몰 연동(예정)
    # 재학습 데이터에는 experience만 쓴다.
    mode: str = Field(default="experience")
    # active: 쇼핑 중 / purchased: 결제 완료 / abandoned: 결제 없이 종료
    status: str = Field(default="active", index=True)
    # 재학습용 분할 (train / eval). 한 번 정하면 바꾸지 않는다.
    split: str | None = None
    # 이 세션에 확률을 낸 모델 버전
    model_version: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True)
    )
    ended_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class View(SQLModel, table=True):
    """상품 조회 원본. 피처는 저장하지 않고 학습과 같은 규칙으로 다시 계산한다."""

    __tablename__ = "views"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", ondelete="CASCADE", index=True)
    item_id: str
    # 조회 시각 (epoch ms). 모델 입력과 같은 단위
    timestamp: int = Field(sa_type=BigInteger)
    # 이 조회 직후 판단한 구매 의도 단계 (browsing / comparing / decided / leaving)
    # 기준값이 바뀌어도 그때 사용자에게 보여준 단계가 남도록 저장한다.
    stage: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True)
    )


class Purchase(SQLModel, table=True):
    """결제 기록. 모델 입력이 아니라 후보 제외와 실제 결제 수 집계에만 쓴다."""

    __tablename__ = "purchases"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", ondelete="CASCADE", index=True)
    item_id: str
    timestamp: int = Field(sa_type=BigInteger)
    # virtual: 체험의 가상 선택 / real: 실제 결제
    kind: str = Field(default="virtual")
    created_at: datetime = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True)
    )
