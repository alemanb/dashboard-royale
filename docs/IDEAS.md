# Ideas & Decisions Log

A running list of ideas we're batting around. Move an item to **Decided** once we commit to it, and note why.

## Open questions

- [ ] **Dashboard tool:** Streamlit / Plotly Dash (Python, easy to host) vs. Tableau Public / Power BI vs. a static HTML page (see `../example-dashboard.html`)
- [ ] **Confirm the model choice with rolling-origin cross-validation** (`StatsForecast.cross_validation`, several origins across Mar–Jun). The single May–Jun holdout ranks MSTL first, but the gap to AutoETS / weekday mean may not survive more origins.
- [ ] **Lead from the model run:** the un-announced Locals Appreciation Week (Jun 9–15) was *not* harder to forecast than other days (MAE inside $54K vs. outside $57K for MSTL). Did the promotion move coin-in at all? Worth a Q2/Q5 look.
- [ ] **Which decision the forecast drives:** technician staffing? promotion weekend timing?
- [ ] **Lean decision rule:** should Lean *choose* the $100K plan from the forecasts (stronger, more work) or only *verify* a plan we pick (fits the time better)?
- [ ] **Originality angle:** what unexpected finding can we chase?

## Ideas

- **Lean 4 as an output checker.** Python computes, exports integer-cent JSON, and Lean proves the budget plan is feasible and the ranking matches its stated metric. A possible "formally verified recommendations" line for the video.

## Decided

- **Architecture: predict → decide → verify.** *Why:* each tool does what it is good at.
  - **Python + DuckDB (analysis):** luck / location / downtime / leak tests and per-machine adjusted metrics. Statistical claims ("machine X was unlucky") live here, with uncertainty shown; Lean can't prove them.
  - **Python (model):** forecast daily coin-in on Jan–Apr, test on May–Jun, compare with a weekday-average baseline, report MAE.
  - **Lean 4 (decide + verify):** Python writes `certificate.json` (all money in integer cents). A Lake executable (`lake exe verify certificate.json`) parses it with `Lean.Json`, applies the decision rule, and checks:
    - budget ≤ $100,000, ≤ 3 action types, quantity limits, no conflicting actions, comp pilot not combined with the floor-wide change
    - **no leakage:** every training date < every test date; every feature's source dates < its prediction date
    - MAE recomputed exactly and matching the dashboard
  - **Dashboard:** a "Verified ✓" panel linking each claim to its check.
- **Core Lean, no Mathlib.** *Why:* integer cents and cross-multiplied ratio comparisons (`a·d < c·b`) need only built-in `Int`/`Nat`; Mathlib adds GBs of download and build time for theorems we don't need. Revisit only if we want proofs about real-valued statistics.
- **Forecast model: MSTL (statsforecast) as the primary model, constant mean and weekday mean as baselines, Chronos-Bolt kept as a comparison row.** *Evidence:* `analysis/01_model_comparison.py`, forecasts of all 61 test days frozen at 2025-05-01, inputs limited to what was knowable that day (events filtered on `announced_date < origin`; no weather or tourism):

  | model | MAE | vs. baseline | time |
  |---|---:|---:|---:|
  | MSTL (trend + weekly season) | $56,343 | −74% | 0.13 s |
  | AutoETS | $63,316 | −71% | 0.13 s |
  | HistGradientBoosting, calendar features | $68,611 | −69% | 0.57 s |
  | weekday mean (guide's beginner model) | $68,699 | −69% | 0.00 s |
  | SeasonalNaive | $72,388 | −67% | 0.13 s |
  | Chronos-Bolt-small, zero-shot (48M params) | $77,369 | −65% | 0.43 s + 5 s load |
  | constant mean (guide's baseline) | $218,258 | 0% | 0.00 s |

  *Why MSTL:* best error, interpretable (a trend plus a weekly pattern a manager can read), gives prediction intervals for the uncertainty requirement, and runs in a tenth of a second so it can be refit live in the dashboard. *Why not a big model:* with 120 training days there is nothing for 48M parameters to learn; the foundation model lost to a weekday average. Speed vs. size is not a real trade-off at this data scale. *Why keep Chronos anyway:* an honest "we tried the fashionable thing and it lost" row is good communication and a candidate originality point.
- **uv for Python environments** (`pyproject.toml` + `uv.lock`), never ad-hoc pip. *Why:* a pip-based setup drifted within an hour (a later install silently upgraded NumPy and broke torch). *Constraint:* development is on an Intel Mac, where PyTorch is capped at 2.2.2, which forces NumPy < 2, pyarrow < 21, scikit-learn < 1.7, and Chronos 1.x instead of Chronos-2. The pins and reasons are commented in `pyproject.toml`.
- **Python calls Lean via `subprocess`**, not LeanInteract (that is for interactive proving, which we don't need).
- **Lean is a multiplier, not a scorer.** It adds credibility to numbers and rules across the rubric, but the statistics and dashboard still carry the grade. Build Python analysis and model first; Lean consumes their outputs.

- **Analysis in Python + DuckDB**, querying Parquet directly. *Why:* the large tables (1.3M rows) need it, and the rest of the stack is Python.
- **Repo is a fork** of `tamu-datathon-org/dashboard-royale`. *Why:* the data is a `0.9.0-draft` release and may change; `git fetch upstream` brings in updates.
