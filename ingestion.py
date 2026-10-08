"""Разбор Excel-журнала счётчиков и расчёт почасового потребления."""
from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

REQUIRED_COLUMNS = {"timestamp", "unit_id", "counter_value"}


class IngestionError(ValueError):
    """Ошибка структуры или содержимого файла (HTTP 422)."""


@dataclass
class IngestionResult:
    frame: pd.DataFrame            # unit_id, timestamp, consumption_kwh, cost_rub
    rows_read: int = 0
    dropped_invalid_rows: int = 0
    dropped_negative_diffs: int = 0
    gaps_detected: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_energy_workbook(file: BinaryIO, tariff_per_kwh: float) -> IngestionResult:
    try:
        raw = pd.read_excel(file, engine="openpyxl", dtype={"unit_id": "string"})
    except Exception as exc:  # битый/неподдерживаемый файл
        raise IngestionError(f"Не удалось прочитать Excel-файл: {exc}") from exc

    raw.columns = [str(c).strip().lower() for c in raw.columns]
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise IngestionError(f"Отсутствуют обязательные колонки: {', '.join(sorted(missing))}")

    df = raw[["timestamp", "unit_id", "counter_value"]].copy()
    rows_read = len(df)

    # --- Типизация и очистка -------------------------------------------------
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["counter_value"] = pd.to_numeric(df["counter_value"], errors="coerce")
    df["unit_id"] = df["unit_id"].astype("string").str.strip()

    before = len(df)
    df = df.dropna(subset=["timestamp", "unit_id", "counter_value"])
    df = df[df["unit_id"] != ""]
    dropped_invalid = before - len(df)

    if df.empty:
        raise IngestionError("В файле нет ни одной валидной строки.")

    # Привести к naive-времени (колонка DateTime без таймзоны)
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_convert(None)

    # Дубликаты (unit_id, timestamp): оставляем последнее показание
    dups = df.duplicated(subset=["unit_id", "timestamp"], keep="last").sum()
    warnings: list[str] = []
    if dups:
        df = df.drop_duplicates(subset=["unit_id", "timestamp"], keep="last")
        warnings.append(f"Удалено дубликатов (unit_id, timestamp): {int(dups)}")

    # --- Группировка, сортировка, разность нарастающего итога ---------------
    df = df.sort_values(["unit_id", "timestamp"]).reset_index(drop=True)
    grouped = df.groupby("unit_id", sort=False)

    df["consumption_kwh"] = grouped["counter_value"].diff()          # C(t) - C(t-1)
    df["gap"] = grouped["timestamp"].diff() > pd.Timedelta(hours=1)  # пропуски в данных

    df = df.dropna(subset=["consumption_kwh"])  # первая строка каждой установки

    # Отрицательная разность = сброс/замена счётчика либо ошибка ввода
    negative = df["consumption_kwh"] < 0
    dropped_negative = int(negative.sum())
    if dropped_negative:
        df = df[~negative]
        warnings.append(
            f"Отброшено строк с отрицательной разностью (сброс/замена счётчика): {dropped_negative}"
        )

    gaps = int(df["gap"].sum())
    if gaps:
        warnings.append(
            f"Обнаружено разрывов во времени > 1 ч: {gaps}. "
            "Потребление за разрыв записано одной суммой на конец интервала."
        )

    if df.empty:
        raise IngestionError("После расчёта разностей не осталось данных (нужно минимум 2 показания на установку).")

    # --- Стоимость -----------------------------------------------------------
    df["cost_rub"] = df["consumption_kwh"] * tariff_per_kwh

    out = df[["timestamp", "unit_id", "consumption_kwh", "cost_rub"]].copy()
    out["unit_id"] = out["unit_id"].astype(str)
    out["consumption_kwh"] = out["consumption_kwh"].astype(float)
    out["cost_rub"] = out["cost_rub"].astype(float)

    return IngestionResult(
        frame=out,
        rows_read=rows_read,
        dropped_invalid_rows=dropped_invalid,
        dropped_negative_diffs=dropped_negative,
        gaps_detected=gaps,
        warnings=warnings,
    )
