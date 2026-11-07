"""Q3: how much play was lost to downtime, and when?

Lost play is valued by WHEN the machine was down: each machine's own coin-in rate for
that local hour (from machine_hour) is applied to the seconds it was unavailable, then
converted to theo with the machine's theo hold. A Saturday-night outage costs more than
a Tuesday-morning one, and this captures that.

Ticket timing from `operations`:  opened -> recorded (detection) -> work_started (waiting
for a tech) -> available (repair).  Waiting is the part a technician action can remove.

Run from the repo root:  uv run python analysis/04_downtime.py
Writes analysis/output/downtime_by_ticket.csv and analysis/output/downtime_by_machine.csv
"""
from pathlib import Path

import duckdb
import pandas as pd

DAILY = "data/1_prepared_views/prepared_daily_view.parquet"
MH = "data/5_optional/machine_hour.parquet"
OPS = "data/2_machine_decision/operations.parquet"
SR = "data/5_optional/shift_roster.parquet"
MACH = "data/2_machine_decision/machines.parquet"
OUT = Path("analysis/output"); OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 220)
con = duckdb.connect()
f = lambda v: f"{v:,.0f}"

# Shifts by local hour (roster: day starts 06:00 local).
con.sql("CREATE MACRO shift_of(h) AS CASE WHEN h BETWEEN 6 AND 13 THEN 'day' WHEN h BETWEEN 14 AND 21 THEN 'swing' ELSE 'grave' END")

# ----------------------------------------------------------------------------
# A. Lost play, valued hour by hour
# ----------------------------------------------------------------------------
con.sql(f"""
CREATE TABLE rate AS                       -- each machine's demand profile by local hour
SELECT machine_id, local_hour,
       SUM(coin_in_cents)::DOUBLE / NULLIF(SUM(available_seconds), 0) AS cents_per_avail_sec
FROM '{MH}' WHERE active AND available_seconds > 0 GROUP BY ALL""")
con.sql(f"""
CREATE TABLE hold AS SELECT machine_id, SUM(theo_usd)/NULLIF(SUM(coin_in_usd),0) AS theo_hold,
       ANY_VALUE(manufacturer) manufacturer, LAST(zone_id ORDER BY gaming_date) zone_id, ANY_VALUE(theme) theme
FROM '{DAILY}' WHERE active GROUP BY 1""")
con.sql(f"""
CREATE TABLE lost AS
SELECT h.machine_id, h.gaming_date, h.local_hour, shift_of(h.local_hour) AS shift,
       strftime(h.gaming_date, '%a') AS weekday, strftime(h.gaming_date, '%Y-%m') AS month,
       (3600 - h.available_seconds) AS down_sec,
       (3600 - h.available_seconds) * COALESCE(r.cents_per_avail_sec, 0) / 100.0 AS lost_coin_in_usd,
       (3600 - h.available_seconds) * COALESCE(r.cents_per_avail_sec, 0) / 100.0 * k.theo_hold AS lost_theo_usd
FROM '{MH}' h LEFT JOIN rate r USING (machine_id, local_hour) JOIN hold k USING (machine_id)
WHERE h.active AND h.available_seconds < 3600""")

tot = con.sql("""SELECT SUM(down_sec)/3600 AS down_hrs, SUM(lost_coin_in_usd) AS lost_coin_in, SUM(lost_theo_usd) AS lost_theo,
                 COUNT(DISTINCT machine_id) machines_affected FROM lost""").df().iloc[0]
sched = float(con.sql(f"SELECT SUM(available_hours/NULLIF(availability_ratio,0)) FROM '{DAILY}' WHERE active").fetchall()[0][0])
floor_theo = float(con.sql(f"SELECT SUM(theo_usd) FROM '{DAILY}' WHERE active").fetchall()[0][0])
print("=== A. Lost play, Jan–Jun 2025 ===")
print(f"  downtime: {tot.down_hrs:,.0f} machine-hours of {sched:,.0f} scheduled ({tot.down_hrs/sched:.2%}); {int(tot.machines_affected)} machines affected")
print(f"  lost coin-in (hour-weighted): ${tot.lost_coin_in:,.0f}")
print(f"  lost theo   (hour-weighted): ${tot.lost_theo:,.0f}  = {tot.lost_theo/floor_theo:.2%} of floor theo ${floor_theo:,.0f}")
flat = float(con.sql(f"""SELECT SUM(theo_usd)/SUM(available_hours) FROM '{DAILY}' WHERE active""").fetchall()[0][0]) * tot.down_hrs
print(f"  (flat estimate, downtime hrs x floor avg theo/hr: ${flat:,.0f}; the hour-weighted number is the honest one)")

print("\n=== When: lost theo by shift / weekday / month ===")
for dim in ["shift", "weekday", "month"]:
    t = con.sql(f"""SELECT {dim}, SUM(down_sec)/3600 down_hrs, SUM(lost_theo_usd) lost_theo,
                    SUM(lost_theo_usd)/NULLIF(SUM(down_sec)/3600,0) lost_per_down_hr FROM lost GROUP BY 1 ORDER BY 1""").df()
    print(t.to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
    print()
hr = con.sql("SELECT local_hour, SUM(down_sec)/3600 down_hrs, SUM(lost_theo_usd) lost_theo FROM lost GROUP BY 1 ORDER BY 1").df()
print("lost theo by local hour (top 6):"); print(hr.nlargest(6, "lost_theo").to_string(index=False, float_format=lambda v: f"{v:,.0f}"))

# ----------------------------------------------------------------------------
# B. Tickets: detection, waiting, repair
# ----------------------------------------------------------------------------
con.sql(f"""
CREATE TABLE tk AS
SELECT o.*, k.manufacturer, k.zone_id, k.theme,
       EPOCH(recorded_at_utc - opened_at_utc)/3600 AS detect_hrs,
       EPOCH(work_started_at_utc - recorded_at_utc)/3600 AS wait_hrs,
       EPOCH(available_at_utc - work_started_at_utc)/3600 AS repair_hrs,
       EPOCH(available_at_utc - opened_at_utc)/3600 AS total_hrs,
       hour(opened_at_local) AS open_hour, shift_of(hour(opened_at_local)) AS open_shift,
       strftime(opened_at_local::DATE, '%a') AS open_weekday
FROM '{OPS}' o JOIN hold k USING (machine_id) WHERE event_type = 'fault_repair'""")
print("\n=== B. Fault tickets: where the hours go ===")
print(con.sql("""SELECT COUNT(*) tickets, SUM(detect_hrs) detect, SUM(wait_hrs) wait, SUM(repair_hrs) repair, SUM(total_hrs) total,
                 SUM(wait_hrs > 0.25) tickets_that_waited, MEDIAN(CASE WHEN wait_hrs > 0.25 THEN wait_hrs END) med_wait_when_waited,
                 MEDIAN(repair_hrs) med_repair FROM tk""").df().to_string(index=False, float_format=lambda v: f"{v:,.1f}"))
print("\nby shift the fault was OPENED in:")
print(con.sql("""SELECT open_shift, COUNT(*) tickets, SUM(wait_hrs > 0.25) waited, SUM(wait_hrs) wait_hrs,
                 MEDIAN(CASE WHEN wait_hrs > 0.25 THEN wait_hrs END) med_wait_when_waited, SUM(repair_hrs) repair_hrs
                 FROM tk GROUP BY 1 ORDER BY 1""").df().to_string(index=False, float_format=lambda v: f"{v:,.1f}"))
print("\nwaiting by hour the fault was opened (hours with the most waiting):")
print(con.sql("""SELECT open_hour, COUNT(*) tickets, SUM(wait_hrs>0.25) waited, SUM(wait_hrs) wait_hrs FROM tk GROUP BY 1 ORDER BY wait_hrs DESC LIMIT 8""").df()
      .to_string(index=False, float_format=lambda v: f"{v:,.1f}"))

# What did WAITING cost? Value the waiting window with the machine's hourly rate.
con.sql("""
CREATE TABLE wait_cost AS
SELECT t.operation_id, t.machine_id, t.open_shift, t.manufacturer, t.wait_hrs,
       SUM(EPOCH(LEAST(h.hour_start_utc + INTERVAL 1 HOUR, t.work_started_at_utc) - GREATEST(h.hour_start_utc, t.recorded_at_utc))
           * COALESCE(r.cents_per_avail_sec,0) / 100.0 * k.theo_hold) AS wait_lost_theo
FROM tk t JOIN '%s' h ON h.machine_id = t.machine_id
     AND h.hour_start_utc < t.work_started_at_utc AND h.hour_start_utc + INTERVAL 1 HOUR > t.recorded_at_utc
LEFT JOIN rate r ON r.machine_id = h.machine_id AND r.local_hour = h.local_hour
JOIN hold k ON k.machine_id = t.machine_id
WHERE t.wait_hrs > 0.25 GROUP BY ALL""" % MH)
print("\n=== Cost of WAITING for a technician (the part an added tech removes) ===")
print(con.sql("""SELECT open_shift, COUNT(*) tickets_waited, SUM(wait_hrs) wait_hrs, SUM(wait_lost_theo) wait_lost_theo
                 FROM wait_cost GROUP BY 1 ORDER BY wait_lost_theo DESC""").df().to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
print("  total waiting cost: $%s theo over 6 months" % f(con.sql("SELECT SUM(wait_lost_theo) FROM wait_cost").fetchall()[0][0]))

# ----------------------------------------------------------------------------
# C. Slot-tech staffing from the roster
# ----------------------------------------------------------------------------
print("\n=== C. Slot technicians on the roster ===")
print(con.sql(f"""SELECT shift, ROUND(AVG(planned),2) planned_per_day, ROUND(AVG(actual),2) actual_per_day,
                  SUM(actual < planned) days_short, COUNT(*) n_days
                  FROM (SELECT gaming_date, shift, SUM(planned_headcount) planned, SUM(actual_headcount) actual
                        FROM '{SR}' WHERE role='slot_tech' GROUP BY 1,2) GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
print("by weekday (actual techs per day, all shifts):")
print(con.sql(f"""SELECT strftime(gaming_date,'%a') wd, shift, ROUND(AVG(a),2) techs FROM
   (SELECT gaming_date, shift, SUM(actual_headcount) a FROM '{SR}' WHERE role='slot_tech' GROUP BY 1,2) GROUP BY 1,2
   ORDER BY shift, CASE wd WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3 WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 WHEN 'Sat' THEN 6 ELSE 7 END""").df()
      .pivot(index="shift", columns="wd", values="techs").to_string())
# Do short-staffed days have longer waits?
print("\nwait when the opening shift was short-staffed vs. fully staffed:")
print(con.sql(f"""WITH staff AS (SELECT gaming_date, shift, SUM(planned_headcount) p, SUM(actual_headcount) a FROM '{SR}' WHERE role='slot_tech' GROUP BY 1,2)
  SELECT CASE WHEN s.a < s.p THEN 'short' ELSE 'full' END staffing, COUNT(*) tickets, ROUND(AVG((t.wait_hrs>0.25)::INT),3) share_waited,
         ROUND(AVG(t.wait_hrs),2) mean_wait_hrs
  FROM tk t JOIN staff s ON s.gaming_date = t.opened_at_local::DATE AND s.shift = t.open_shift GROUP BY 1""").df().to_string(index=False))

# ----------------------------------------------------------------------------
# D. Ridgeline: brand or age? Trend? Repeat offenders? Cost per machine-day.
# ----------------------------------------------------------------------------
print("\n=== D. Faults by manufacturer and install year ===")
print(con.sql(f"""SELECT k.manufacturer, year(m.install_date) AS yr, COUNT(DISTINCT k.machine_id) machines,
   ROUND(SUM(d.faults_opened) / COUNT(*) * 181, 1) faults_per_machine_6mo
   FROM '{DAILY}' d JOIN hold k USING (machine_id) JOIN '{MACH}' m USING (machine_id) WHERE d.active
   GROUP BY 1,2 ORDER BY 1,2""").df().pivot(index="yr", columns="manufacturer", values="faults_per_machine_6mo").to_string())
print("\nfault rate by month (faults per 100 machine-days):")
print(con.sql(f"""SELECT month, manufacturer, ROUND(100.0*SUM(faults_opened)/COUNT(*),2) r FROM '{DAILY}' WHERE active GROUP BY 1,2 ORDER BY 1""").df()
      .pivot(index="month", columns="manufacturer", values="r").to_string())
print("\nrepeat offenders (most faults):")
print(con.sql("""SELECT machine_id, manufacturer, theme, zone_id, COUNT(*) faults, SUM(total_hrs) down_hrs, SUM(direct_cost_cents)/100 repair_usd
                 FROM tk GROUP BY ALL ORDER BY faults DESC LIMIT 8""").df().to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
print("\nall-in service cost per machine-day (contract + repairs), by manufacturer:")
print(con.sql(f"""SELECT manufacturer, COUNT(*) machine_days, ROUND(SUM(service_cost_usd)/COUNT(*),2) contract_per_day,
   ROUND(SUM(repair_cost_usd)/COUNT(*),2) repair_per_day, ROUND(SUM(service_cost_usd+repair_cost_usd)/COUNT(*),2) total_per_day
   FROM '{DAILY}' WHERE active GROUP BY 1 ORDER BY total_per_day DESC""").df().to_string(index=False))
print("\nlost theo by manufacturer (hour-weighted):")
print(con.sql("""SELECT k.manufacturer, SUM(l.down_sec)/3600 down_hrs, SUM(l.lost_theo_usd) lost_theo
                 FROM lost l JOIN hold k USING (machine_id) GROUP BY 1 ORDER BY 3 DESC""").df().to_string(index=False, float_format=lambda v: f"{v:,.0f}"))

con.sql("SELECT * FROM tk").df().to_csv(OUT / "downtime_by_ticket.csv", index=False)
con.sql("""SELECT machine_id, SUM(down_sec)/3600 down_hrs, SUM(lost_coin_in_usd) lost_coin_in, SUM(lost_theo_usd) lost_theo
           FROM lost GROUP BY 1""").df().to_csv(OUT / "downtime_by_machine.csv", index=False)
print(f"\nWrote {OUT/'downtime_by_ticket.csv'}, {OUT/'downtime_by_machine.csv'}")
