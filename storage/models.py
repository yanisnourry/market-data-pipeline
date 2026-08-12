from decimal import Decimal
from sqlalchemy import Numeric, DateTime, String, text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime


class Base(DeclarativeBase):
    pass


class CandleModel(Base):
    __tablename__ = "candles"

    exchange: Mapped[str] = mapped_column(String(20), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, primary_key=True)
    has_gap: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_inconsistency: Mapped[bool] = mapped_column(Boolean, nullable=False)

async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE)"
        ))
