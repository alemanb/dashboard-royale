"""Rolling-origin cross-validation of the daily floor coin-in forecasters.

Instead of one holdout (origin May 1), stand at the start of each month from March
to June, train on everything before it, forecast that whole month, and score.
Every fold respects time: train dates < test dates, asserted per fold.

Run from the repo root:  uv run python analysis/02_rolling_cv.py
"""
import time
import warnings

import duckdb
import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, MSTL, SeasonalNaive

warnings.filterwarnings("ignore")

FLOOR = "data/1_prepared_views/property_day.parquet"
ORIGINS = [pd.Timestamp(d) for d in ["2025-03-01", "2025-04-01", "2025-05-01", "2025-06-01"]]
END = pd.Timestamp("2025-07-01")  # exclusive

floor = duckdb.sql(f"SELECT gaming_date::DATE AS ds, coin_in_usd AS y FROM '{FLOOR}' ORDER BY ds").df()
floor["ds"] = pd.to_datetime(floor["ds"])
floor["weekday"] = floor["ds"].dt.weekday

try:
    import torch
    from chronos import BaseChronosPipeline
    chronos = BaseChronosPipeline.from_pretrained("amazon/chronos-bolt-small",
                                                  device_map="cpu", torch_dtype=torch.float32)
except Exception as e:  # noqa: BLE001
    chronos = None
    print("Chronos unavailable:", type(e).__name__)

rows = []
for i, origin in enumerate(ORIGINS):
    test_end = ORIGINS[i + 1] if i + 1 < len(ORIGINS) else END
    train = floor[floor["ds"] < origin]
    test = floor[(floor["ds"] >= origin) & (floor["ds"] < test_end)]
    h = len(test)
    assert train["ds"].max() < test["ds"].min(), "leakage: training data overlaps test"
    y = test["y"].to_numpy()
    preds = {}

    preds["constant_mean"] = np.full(h, train["y"].mean())
    preds["weekday_mean"] = test["weekday"].map(train.groupby("weekday")["y"].mean()).to_numpy()

    sf = StatsForecast(
        models=[SeasonalNaive(season_length=7), AutoETS(season_length=7),
                MSTL(season_length=7, trend_forecaster=AutoETS(model="ZZN"))],
        freq="D", fallback_model=SeasonalNaive(season_length=7))
    fc = sf.forecast(df=train[["ds", "y"]].assign(unique_id="floor"), h=h)
    for m in ["SeasonalNaive", "AutoETS", "MSTL"]:
        preds[m] = fc[m].to_numpy()

    if chronos is not None:
        q, _ = chronos.predict_quantiles(context=torch.tensor(train["y"].to_numpy(), dtype=torch.float32),
                                         prediction_length=h, quantile_levels=[0.5])
        preds["Chronos-Bolt"] = q[0, :, 0].numpy()

    for name, p in preds.items():
        rows.append({"fold": f"{origin:%b} (train {len(train)}d)", "model": name,
                     "mae": float(np.mean(np.abs(y - p)))})

res = pd.DataFrame(rows)
table = res.pivot(index="model", columns="fold", values="mae")
table = table[list(res["fold"].unique())]  # chronological, not alphabetical
table["mean"] = table.mean(axis=1)
table["worst"] = table.drop(columns="mean").max(axis=1)
ref = table.loc["weekday_mean"].drop(["mean", "worst"])
table["beats weekday_mean"] = [
    f"{int((table.loc[m].drop(['mean', 'worst']) < ref).sum())}/{len(ref)}" for m in table.index]
table = table.sort_values("mean")

pd.set_option("display.width", 200)
print("\n=== Rolling-origin CV: MAE ($) per fold, forecasting the whole next month ===")
print(table.to_string(float_format=lambda v: f"{v:,.0f}"))

# Fold-by-fold winner: is one model consistently best, or does it depend on the month?
print("\nBest model per fold:")
for fold in [c for c in table.columns if "(" in c]:
    print(f"  {fold:<22} {table[fold].idxmin():<14} ${table[fold].min():,.0f}")
