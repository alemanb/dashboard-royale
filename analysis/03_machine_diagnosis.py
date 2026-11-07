"""Q1: which machines are truly underperforming once exposure, availability and luck are accounted for?

For every machine, over its days on the floor:
  * exposure:      days on floor, available hours
  * availability:  available hours / scheduled hours        -> downtime
  * demand:        theo per available hour                  -> location / exposure
  * luck:          z = (house_win - theo) / sd               -> luck vs. leak
Two sd estimates are computed. `sd_formula` comes from game_math's payout variance and
turned out to UNDERSTATE real variance by ~24% (bet sizes vary within a day, so
coin_in^2/spins is smaller than the true sum of squared bets). `sd_emp` is each machine's
own observed day-to-day residual variance and is used as the primary z.
Then: verdicts on the GM's raw bottom 10, our alternative ranking, and whether the
machines with extreme z cluster on a game, manufacturer or zone.

Run from the repo root:  uv run python analysis/03_machine_diagnosis.py
Writes analysis/output/machine_diagnosis.csv
"""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

DAILY = "data/1_prepared_views/prepared_daily_view.parquet"
GAMES = "data/2_machine_decision/game_math.parquet"
CAL = "data/2_machine_decision/calendar_day.parquet"
OPS = "data/2_machine_decision/operations.parquet"
OUT = Path("analysis/output"); OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 220)

# ----------------------------------------------------------------------------
# Per-machine aggregates. Variance of the luck residual is summed per day-row:
#   var_day = avg_bet^2 * spins * payout_variance = coin_in^2 * payout_variance / spins
# so a machine whose game setting changed mid-period is still handled correctly.
# ----------------------------------------------------------------------------
m = duckdb.sql(f"""
    WITH d AS (
        SELECT d.*, c.scheduled_seconds / 3600.0 AS scheduled_hours, g.payout_multiplier_variance AS pv
        FROM '{DAILY}' d
        JOIN '{CAL}' c USING (gaming_date)
        JOIN '{GAMES}' g USING (config_id)
        WHERE d.active                                   -- drop not_installed / retired rows
    )
    SELECT machine_id,
           ANY_VALUE(manufacturer)                          AS manufacturer,
           LAST(config_id ORDER BY gaming_date)             AS config_id,
           LAST(theme ORDER BY gaming_date)                 AS theme,
           LAST(volatility_class ORDER BY gaming_date)      AS volatility,
           LAST(zone_id ORDER BY gaming_date)               AS zone_id,
           LAST(bank_id ORDER BY gaming_date)               AS bank_id,
           COUNT(DISTINCT zone_id)                          AS zones_seen,
           COUNT(DISTINCT config_id)                        AS configs_seen,
           COUNT(*)                                         AS days_on_floor,
           MIN(gaming_date)                                 AS first_day,
           MAX(gaming_date)                                 AS last_day,
           SUM(available_hours)                             AS avail_hours,
           SUM(scheduled_hours)                             AS sched_hours,
           SUM(available_hours) / SUM(scheduled_hours)      AS availability,
           SUM(occupied_hours) / NULLIF(SUM(available_hours), 0) AS occupancy,
           SUM(faults_opened)                               AS faults,
           SUM(paid_spins)                                  AS spins,
           SUM(coin_in_usd)                                 AS coin_in,
           SUM(house_win_usd)                               AS house_win,
           SUM(theo_usd)                                    AS theo,
           SUM(house_win_usd) / NULLIF(SUM(coin_in_usd), 0) AS hold,
           SUM(theo_usd)      / NULLIF(SUM(coin_in_usd), 0) AS theo_hold,
           SQRT(SUM(coin_in_usd::DOUBLE * coin_in_usd::DOUBLE * pv / NULLIF(paid_spins, 0))) AS sd_formula,
           SQRT(VAR_SAMP(house_win_usd::DOUBLE - theo_usd::DOUBLE) * COUNT(*))                AS sd_emp,
           SUM(theo_usd) / NULLIF(SUM(available_hours), 0)  AS theo_per_hr,
           SUM(coin_in_usd) / NULLIF(SUM(available_hours), 0) AS coin_in_per_hr,
           SUM(lease_cost_usd + service_cost_usd + power_cost_usd + repair_cost_usd) AS supplied_costs
    FROM d GROUP BY machine_id
""").df()
m["luck_usd"] = m["house_win"] - m["theo"]
m["z_formula"] = m["luck_usd"] / m["sd_formula"]
m["z"] = m["luck_usd"] / m["sd_emp"]            # primary: empirical variance
m["var_ratio"] = (m["sd_emp"] / m["sd_formula"]) ** 2   # >1 means the formula understated variance
m["theo_per_hr_pct"] = m["theo_per_hr"].rank(pct=True)   # percentile among all machines
N = len(m)

# Zone-level demand, to say what "a quiet spot" means in numbers.
zone = (m.groupby("zone_id").agg(machines=("machine_id", "count"), theo_per_hr=("theo", "sum"),
                                 hrs=("avail_hours", "sum"))
          .assign(theo_per_hr=lambda z: z["theo_per_hr"] / z["hrs"]).sort_values("theo_per_hr"))
floor_theo_per_hr = m["theo"].sum() / m["avail_hours"].sum()

# ----------------------------------------------------------------------------
# Verdict rules. Order matters: exposure first, then downtime, then demand, then luck.
# ----------------------------------------------------------------------------
FULL = 170  # days; the period has 181 gaming days
def verdict(r):
    flags = []
    if r.days_on_floor < FULL:
        flags.append(f"short tenure ({r.days_on_floor}d)")
    if r.availability < 0.97:
        flags.append(f"downtime (avail {r.availability:.1%}, {int(r.faults)} faults)")
    if r.theo_per_hr_pct < 0.25:
        flags.append(f"quiet spot (theo/hr p{r.theo_per_hr_pct*100:.0f}, zone {r.zone_id})")
    if r.z < -3:
        flags.append(f"INSPECT (z {r.z:+.1f})")
    elif r.z < -2:
        flags.append(f"unlucky (z {r.z:+.1f})")
    elif abs(r.z) <= 2:
        flags.append(f"normal luck (z {r.z:+.1f})")
    else:
        flags.append(f"lucky (z {r.z:+.1f})")
    return "; ".join(flags)
m["verdict"] = m.apply(verdict, axis=1)

cols = ["machine_id", "theme", "volatility", "zone_id", "days_on_floor", "availability",
        "theo_per_hr", "house_win", "theo", "z", "verdict"]
fmt = {"availability": "{:.3f}".format, "theo_per_hr": "{:,.1f}".format, "house_win": "{:,.0f}".format,
       "theo": "{:,.0f}".format, "z": "{:+.1f}".format}

print(f"Machines: {N}.  Floor theo per available hour: ${floor_theo_per_hr:,.2f}")
print("\n=== Zones ranked by demand (theo per available machine-hour) ===")
print(zone.to_string(float_format=lambda v: f"{v:,.2f}"))

print("\n=== The GM's list: raw bottom 10 by house win, with our verdicts ===")
gm10 = m.nsmallest(10, "house_win")
print(gm10[cols].to_string(index=False, formatters=fmt))

print("\n=== Our bottom 10 by demand (theo per available hour), full-tenure machines only ===")
ours = m[m.days_on_floor >= FULL].nsmallest(10, "theo_per_hr")
print(ours[cols].to_string(index=False, formatters=fmt))
print("Overlap with GM's list:", sorted(set(gm10.machine_id) & set(ours.machine_id)))

# ----------------------------------------------------------------------------
# Luck: how many extreme machines should there be, and do they cluster?
# ----------------------------------------------------------------------------
print("\n=== Luck test across the floor (empirical z primary; formula z for comparison) ===")
print(f"  variance ratio (observed / formula): median {m.var_ratio.median():.2f} -> formula sd too small by ~{(np.sqrt(m.var_ratio.median())-1)*100:.0f}%")
print(f"  {'threshold':<10}{'expected':>9}{'obs (emp z)':>13}{'obs (formula z)':>17}")
for thr in [-2, -2.5, -3]:
    print(f"  z < {thr:<5} {N*norm.cdf(thr):9.1f} {int((m.z < thr).sum()):13d} {int((m.z_formula < thr).sum()):17d}")
print(f"  z > +2.5  {N*norm.sf(2.5):9.1f} {int((m.z > 2.5).sum()):13d} {int((m.z_formula > 2.5).sum()):17d}")
print(f"  sd of empirical z {m.z.std():.2f}, of formula z {m.z_formula.std():.2f}  (pure luck: 1.00)")

low = m[(m.z < -2) | (m.z_formula < -2.5)]
print(f"\n=== {len(low)} machines below z = -2 (empirical) or -2.5 (formula): do they cluster? ===")
print(low.sort_values("z")[["machine_id", "theme", "volatility", "manufacturer", "zone_id", "faults",
                            "hold", "theo_hold", "z", "z_formula", "var_ratio", "luck_usd"]]
      .to_string(index=False, formatters={"hold": "{:.3f}".format, "theo_hold": "{:.3f}".format,
                                          "z": "{:+.1f}".format, "z_formula": "{:+.1f}".format,
                                          "var_ratio": "{:.2f}".format, "luck_usd": "{:,.0f}".format}))
for dim in ["theme", "manufacturer", "zone_id", "volatility"]:
    share_low = low[dim].value_counts(normalize=True)
    share_all = m[dim].value_counts(normalize=True)
    lift = (share_low / share_all).dropna().sort_values(ascending=False)
    top = lift.index[0]
    print(f"  {dim:<13} most over-represented: {top:<16} {share_low[top]:.0%} of low-z vs {share_all[top]:.0%} of floor "
          f"(lift {lift.iloc[0]:.1f}x; {int(low[dim].eq(top).sum())} of {int(m[dim].eq(top).sum())} such machines)")

# Mean z by game: a game-level shift would show up here (pure luck: all near 0).
print("\n=== Mean z by game title (pure luck: all near 0, spread ~ 1/sqrt(n)) ===")
g = m.groupby(["theme", "volatility"]).agg(n=("z", "size"), mean_z=("z", "mean"),
                                           hold=("house_win", "sum"), coin=("coin_in", "sum"),
                                           theo=("theo", "sum"))
g["hold"] = g["hold"] / g["coin"]; g["theo_hold"] = g["theo"] / g["coin"]
g["se"] = 1 / np.sqrt(g["n"])
print(g[["n", "mean_z", "se", "hold", "theo_hold"]].sort_values("mean_z")
      .to_string(float_format=lambda v: f"{v:.3f}"))

# Is any low-z machine's shortfall concentrated in time (e.g. after a config change)?
print("\n=== Monthly z for the three most extreme machines ===")
worst3 = list(low.sort_values("z").machine_id[:3])
mz = duckdb.sql(f"""
    SELECT machine_id, month,
           (SUM(house_win_usd) - SUM(theo_usd)) /
             SQRT(VAR_SAMP(house_win_usd::DOUBLE - theo_usd::DOUBLE) * COUNT(*)) AS z
    FROM '{DAILY}' d
    WHERE d.active AND machine_id IN ({','.join(repr(x) for x in worst3)})
    GROUP BY ALL ORDER BY machine_id, month
""").df()
print(mz.pivot(index="machine_id", columns="month", values="z").to_string(float_format=lambda v: f"{v:+.1f}"))

# Downtime leaders, for Q3 later.
print("\n=== Lowest availability (downtime leaders) ===")
print(m.nsmallest(8, "availability")[["machine_id", "theme", "manufacturer", "zone_id", "days_on_floor",
                                       "availability", "faults", "theo_per_hr"]]
      .to_string(index=False, formatters={"availability": "{:.3f}".format, "theo_per_hr": "{:,.1f}".format}))

m.to_csv(OUT / "machine_diagnosis.csv", index=False)
print(f"\nWrote {OUT/'machine_diagnosis.csv'} ({N} rows)")
