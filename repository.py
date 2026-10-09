from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import EnergyLog

CHUNK = 5000  # 4 колонки * 5000 << лимита 65535 параметров


def bulk_upsert_energy_logs(db: Session, frame: pd.DataFrame) -> int:
    """Пакетная вставка с обновлением при конфликте (unit_id, timestamp)."""
    records = frame.to_dict(orient="records")
    for i in range(0, len(records), CHUNK):
        chunk = records[i : i + CHUNK]
        stmt = pg_insert(EnergyLog).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_energy_unit_ts",
            set_={
                "consumption_kwh": stmt.excluded.consumption_kwh,
                "cost_rub": stmt.excluded.cost_rub,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(records)


def list_units(db: Session) -> list[str]:
    return list(db.scalars(select(EnergyLog.unit_id).distinct().order_by(EnergyLog.unit_id)))


def query_energy(
    db: Session,
    unit_id: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
) -> list[EnergyLog]:
    stmt = select(EnergyLog)
    if unit_id:
        stmt = stmt.where(EnergyLog.unit_id == unit_id)
    if start_date:
        stmt = stmt.where(EnergyLog.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(EnergyLog.timestamp <= end_date)
    stmt = stmt.order_by(EnergyLog.timestamp, EnergyLog.unit_id).limit(limit)
    return list(db.scalars(stmt))