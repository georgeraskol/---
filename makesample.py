"""Генератор тестового Excel: python make_sample.py"""
import numpy as np
import pandas as pd

ts = pd.date_range("2026-10-01", periods=72, freq="h")
rows = []
for unit, base in [("AVT-10", 1_000_000), ("KAT-RIF-2", 500_000)]:
    counter = base + np.cumsum(np.random.uniform(800, 1200, len(ts)))
    rows += [{"timestamp": t, "unit_id": unit, "counter_value": round(c, 2)} for t, c in zip(ts, counter)]
pd.DataFrame(rows).to_excel("sample_energy_log.xlsx", index=False)