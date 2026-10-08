import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.schemas import EnergyLogOut, UploadResult
from app.services.ingestion import IngestionError, parse_energy_workbook
from app.services import repository

logger = logging.getLogger("ems")
settings = get_settings()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Для продакшена вместо create_all используйте Alembic-миграции.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="LUKOIL Energy Management System API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/api/v1/upload-log/", response_model=UploadResult)
def upload_log(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # sync-endpoint: FastAPI выполнит его в threadpool, event loop не блокируется Pandas.
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Допускаются только файлы .xlsx")

    content = file.file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ")

    try:
        result = parse_energy_workbook(io.BytesIO(content), settings.TARIFF_PER_KWH)
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        saved = repository.bulk_upsert_energy_logs(db, result.frame)
    except Exception:
        db.rollback()
        logger.exception("Ошибка записи в БД")
        raise HTTPException(status_code=500, detail="Ошибка сохранения данных в базу")

    return UploadResult(
        filename=file.filename,
        rows_read=result.rows_read,
        rows_saved=saved,
        units=sorted(result.frame["unit_id"].unique().tolist()),
        tariff_per_kwh=settings.TARIFF_PER_KWH,
        dropped_invalid_rows=result.dropped_invalid_rows,
        dropped_negative_diffs=result.dropped_negative_diffs,
        gaps_detected=result.gaps_detected,
        warnings=result.warnings,
    )


@app.get("/api/v1/units/", response_model=list[str])
def get_units(db: Session = Depends(get_db)):
    return repository.list_units(db)


@app.get("/api/v1/energy-data/", response_model=list[EnergyLogOut])
def get_energy_data(
    unit_id: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(50000, ge=1, le=200000),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date не может быть позже end_date")
    return repository.query_energy(db, unit_id, start_date, end_date, limit)
