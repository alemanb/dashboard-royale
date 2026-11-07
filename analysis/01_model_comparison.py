"""Compare forecasting approaches for daily floor coin-in, all under the same honest protocol.

Protocol (matches GUIDE.md §7):
  * Forecast origin = 2025-05-01. Train on Jan 1 – Apr 30 (120 days).
  * Forecast ALL 61 test days (May 1 – Jun 30) at once, then freeze. No peeking.
  * Future inputs may only be things knowable on May 1: calendar, holidays, and
    events whose `announced_date` < origin. Weather and tourism are NOT knowable.
  * Score = MAE in dollars on the 61 test days. Also record wall-clock time.

Run from the repo root:  .venv/bin/python analysis/01_model_comparison.py
"""
import time
import warnings

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

FLOOR = "data/1_prepared_views/property_day.parquet"
CAL = "data/2_machine_decision/calendar_day.parquet"
EVENTS = "data/4_context/events.parquet"
ORIGIN = pd.Timestamp("2025-05-01")
H = 61  # days in May + June

# ----------------------------------------------------------------------------
# Data: one row per gaming day, with only forecast-time-legal covariates
# ----------------------------------------------------------------------------
floor = duckdb.sql(f"""
    SELECT p.gaming_date::DATE AS ds, p.coin_in_usd AS y,
           c.local_weekday, c.is_weekend, c.federal_holiday IS NOT NULL AS is_holiday
    FROM '{FLOOR}' p JOIN '{CAL}' c USING (gaming_date)
    ORDER BY ds
""").df()
floor["ds"] = pd.to_datetime(floor["ds"])
events = duckdb.sql(f"SELECT * FROM '{EVENTS}'").df()
for c in ["start_date", "end_date", "announced_date"]:
    events[c] = pd.to_datetime(events[c])

# Leakage guard: an event only counts if it was announced before the forecast origin.
known = events[events["announced_date"] < ORIGIN]
unknown = events[events["announced_date"] >= ORIGIN]
print("Events known on May 1:", list(known["event_id"]))
print("Events NOT knowable on May 1 (excluded as inputs):", list(unknown["event_id"]),
      "-", "; ".join(f"{r.name} {r.start_date.date()}–{r.end_date.date()}" for r in unknown.itertuples()))

def n_active(d, ev):
    return int(((ev["start_date"] <= d) & (d <= ev["end_date"])).sum())

floor["events_known"] = floor["ds"].map(lambda d: n_active(d, known))
floor["weekday_num"] = floor["ds"].dt.weekday
floor["t"] = np.arange(len(floor))  # trend index

train = floor[floor["ds"] < ORIGIN].copy()
test = floor[floor["ds"] >= ORIGIN].copy()
assert len(test) == H and train["ds"].max() < test["ds"].min()
y_true = test["y"].to_numpy()

results = []

def score(name, pred, seconds, note=""):
    pred = np.asarray(pred, dtype=float)
    mae = np.mean(np.abs(y_true - pred))
    results.append((name, mae, seconds, note))
    test[name] = pred

# ----------------------------------------------------------------------------
# 1. Baselines (what the guide suggests)
# ----------------------------------------------------------------------------
t0 = time.perf_counter()
score("constant_mean", np.full(H, train["y"].mean()), time.perf_counter() - t0, "guide's baseline")

t0 = time.perf_counter()
wk = train.groupby("weekday_num")["y"].mean()
score("weekday_mean", test["weekday_num"].map(wk), time.perf_counter() - t0, "guide's beginner model")

# ----------------------------------------------------------------------------
# 2. Classical statistical models (statsforecast)
# ----------------------------------------------------------------------------
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, MSTL, SeasonalNaive

sf_train = train[["ds", "y"]].assign(unique_id="floor")
sf = StatsForecast(
    models=[SeasonalNaive(season_length=7),
            AutoETS(season_length=7),
            MSTL(season_length=7, trend_forecaster=AutoETS(model="ZZN"))],
    freq="D", fallback_model=SeasonalNaive(season_length=7),
)
t0 = time.perf_counter()
fc = sf.forecast(df=sf_train, h=H)
sf_secs = time.perf_counter() - t0
for col in ["SeasonalNaive", "AutoETS", "MSTL"]:
    score(col, fc[col].to_numpy(), sf_secs / 3, "statsforecast")

# ----------------------------------------------------------------------------
# 3. Gradient-boosted trees on calendar + known-event features (scikit-learn)
#    No lag features: a 61-day-ahead forecast can't use yesterday's value.
# ----------------------------------------------------------------------------
from sklearn.ensemble import HistGradientBoostingRegressor

feats = ["weekday_num", "is_weekend", "is_holiday", "events_known", "t"]
t0 = time.perf_counter()
gbm = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300, learning_rate=0.05,
                                    max_leaf_nodes=8, min_samples_leaf=5,
                                    categorical_features=[0], random_state=0)
gbm.fit(train[feats].astype(float), train["y"])
score("HistGBM_calendar", gbm.predict(test[feats].astype(float)), time.perf_counter() - t0,
      "sklearn; weekday+holiday+known events+trend")

# ----------------------------------------------------------------------------
# 4. Pretrained foundation model, zero-shot (Amazon Chronos-Bolt, Hugging Face)
#    Sees ONLY the 120 training values. No covariates. Runs on CPU.
# ----------------------------------------------------------------------------
try:
    import torch
    from chronos import BaseChronosPipeline

    t0 = time.perf_counter()
    pipe = BaseChronosPipeline.from_pretrained("amazon/chronos-bolt-small",
                                               device_map="cpu", torch_dtype=torch.float32)
    load_secs = time.perf_counter() - t0
    t0 = time.perf_counter()
    q, mean = pipe.predict_quantiles(context=torch.tensor(train["y"].to_numpy(), dtype=torch.float32),
                                     prediction_length=H, quantile_levels=[0.1, 0.5, 0.9])
    pred_secs = time.perf_counter() - t0
    score("Chronos-Bolt-small", q[0, :, 1].numpy(), pred_secs,
          f"HF zero-shot, 48M params; +{load_secs:.1f}s model load")
except Exception as e:  # keep the comparison alive if the download fails
    print("Chronos skipped:", type(e).__name__, str(e)[:120])

# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
print(f"\n=== MAE on May 1 – Jun 30 (61 days), forecasts frozen at {ORIGIN.date()} ===")
print(f"{'model':<20}{'MAE ($)':>12}{'vs baseline':>13}{'time (s)':>10}  note")
base = results[0][1]
for name, mae, secs, note in sorted(results, key=lambda r: r[1]):
    print(f"{name:<20}{mae:>12,.0f}{(1 - mae / base) * 100:>12.0f}%{secs:>10.2f}  {note}")

# Where do the errors come from? The promotion nobody could know about on May 1.
locals_wk = (test["ds"] >= "2025-06-09") & (test["ds"] <= "2025-06-15")
print("\nMAE inside vs outside the un-announced Locals Appreciation Week (Jun 9–15):")
for name, *_ in sorted(results, key=lambda r: r[1])[:4]:
    err = (test["y"] - test[name]).abs()
    print(f"  {name:<20} inside ${err[locals_wk].mean():>9,.0f}   outside ${err[~locals_wk].mean():>9,.0f}")
