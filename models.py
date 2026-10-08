from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EnergyLog(Base):
    __tablename__ = "energy_logs"
    # Уникальность нужна для идемпотентной повторной загрузки (upsert).
    __table_args__ = (UniqueConstraint("unit_id", "timestamp", name="uq_energy_unit_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    unit_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    consumption_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    cost_rub: Mapped[float] = mapped_column(Float, nullable=False)
