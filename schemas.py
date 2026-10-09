from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EnergyLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    unit_id: str
    consumption_kwh: float
    cost_rub: float


class UploadResult(BaseModel):
    filename: str
    rows_read: int
    rows_saved: int
    units: list[str]
    tariff_per_kwh: float
    dropped_invalid_rows: int
    dropped_negative_diffs: int   # сброс/замена счётчика
    gaps_detected: int            # пропущенные часы (разрыв > 1 ч)
    warnings: list[str]