"""Teaching demo: how the luck test and the forecast model work on the real data.

Run from the repo root:  .venv/bin/python analysis/00_demo_stats_and_model.py
"""
import duckdb

DAILY = "data/1_prepared_views/prepared_daily_view.parquet"
GAMES = "data/2_machine_decision/game_math.parquet"
FLOOR = "data/1_prepared_views/property_day.parquet"

# ---------------------------------------------------------------------------
# PART 1 — STATISTICS: is a low-earning machine bad, or just unlucky?
#
# Each spin pays bet × M, where M is a random multiplier with
#   mean     = RTP                          (e.g. 0.92)
#   variance = payout_multiplier_variance   (from game_math)
# Over N spins at average bet b, the house win is a sum of N random draws, so
#   expected house win (theo) = coin_in × (1 − RTP)
#   standard deviation        ≈ b × √(N × variance)
#   z = (actual − theo) / sd   → "how many normal swings away from expected"
# |z| < 2 is ordinary luck; z < −3 is very unlikely to be luck alone.
# ---------------------------------------------------------------------------
per_machine = duckdb.sql(f"""
    WITH m AS (
        SELECT d.machine_id, d.config_id, d.volatility_class, d.configured_rtp,
               SUM(d.house_win_usd)      AS house_win,
               SUM(d.theo_usd)           AS theo,
               SUM(d.coin_in_usd)        AS coin_in,
               SUM(d.paid_spins)         AS spins,
               SUM(d.available_hours)    AS avail_hours
        FROM '{DAILY}' d
        WHERE d.location_id IS NOT NULL          -- drop off-floor days
        GROUP BY ALL
    )
    SELECT m.*,
           house_win / NULLIF(coin_in, 0)                              AS hold,
           (coin_in / NULLIF(spins, 0)) * SQRT(spins * g.payout_multiplier_variance) AS sd,
           (house_win - theo) /
             NULLIF((coin_in / NULLIF(spins, 0)) * SQRT(spins * g.payout_multiplier_variance), 0) AS z,
           theo / NULLIF(avail_hours, 0)                               AS theo_per_hour
    FROM m JOIN '{GAMES}' g USING (config_id)
""").df()

cols = ["machine_id", "volatility_class", "house_win", "theo", "hold", "configured_rtp", "z", "theo_per_hour"]
fmt = {"house_win": "{:,.0f}".format, "theo": "{:,.0f}".format, "hold": "{:.3f}".format,
       "z": "{:+.1f}".format, "theo_per_hour": "{:,.2f}".format}

print("=== The GM's list: bottom 10 by raw house win ===")
print(per_machine.nsmallest(10, "house_win")[cols].to_string(index=False, formatters=fmt))

print("\n=== Same machines, read the z column ===")
print("z near 0 → earned what the math expected.  Large negative z → unlucky OR leaking.")
print("Low theo_per_hour → it simply gets little play (location / exposure problem).")

print("\n=== Most suspicious by luck test (lowest z) ===")
print(per_machine.nsmallest(10, "z")[cols].to_string(index=False, formatters=fmt))

# ---------------------------------------------------------------------------
# PART 2 — MODEL: forecast daily floor coin-in, judged on data it never saw
#
# Train = Jan–Apr, Test = May–Jun (split by TIME, never randomly).
# Baseline: predict the same constant (training mean) every day.
# Model:    predict the training average for that weekday.
# Score:    MAE = average |actual − predicted| in dollars. Lower is better.
# ---------------------------------------------------------------------------
floor = duckdb.sql(f"SELECT * FROM '{FLOOR}'").df()
coin_col = next(c for c in floor.columns if "coin_in" in c and c.endswith("usd"))
floor["weekday"] = floor["gaming_date"].astype("datetime64[ns]").dt.day_name()
train = floor[floor["gaming_date"].astype(str) < "2025-05-01"]
test = floor[floor["gaming_date"].astype(str) >= "2025-05-01"].copy()

test["baseline"] = train[coin_col].mean()
test["weekday_model"] = test["weekday"].map(train.groupby("weekday")[coin_col].mean())

mae = lambda col: (test[coin_col] - test[col]).abs().mean()
print(f"\n=== Forecast of daily floor {coin_col} (train Jan–Apr, test May–Jun) ===")
print(f"Baseline (constant mean) MAE: ${mae('baseline'):,.0f}")
print(f"Weekday-average model    MAE: ${mae('weekday_model'):,.0f}")
print("\nTraining weekday averages (what the model 'learned'):")
print(train.groupby("weekday")[coin_col].mean().sort_values().map("${:,.0f}".format).to_string())
