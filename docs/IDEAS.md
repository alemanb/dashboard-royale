# Ideas & Decisions Log

A running list of ideas we're batting around. Move an item to **Decided** once we commit to it, and note why.

## Open questions

- [ ] **Dashboard tool:** Streamlit / Plotly Dash (Python, easy to host) vs. Tableau Public / Power BI vs. a static HTML page (see `../example-dashboard.html`)
- [ ] **Forecast model:** weekday-average baseline vs. something stronger (e.g. weekday + event/holiday effects, gradient boosting) for daily floor coin-in
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
- **Python calls Lean via `subprocess`**, not LeanInteract (that is for interactive proving, which we don't need).
- **Lean is a multiplier, not a scorer.** It adds credibility to numbers and rules across the rubric, but the statistics and dashboard still carry the grade. Build Python analysis and model first; Lean consumes their outputs.

- **Analysis in Python + DuckDB**, querying Parquet directly. *Why:* the large tables (1.3M rows) need it, and the rest of the stack is Python.
- **Repo is a fork** of `tamu-datathon-org/dashboard-royale`. *Why:* the data is a `0.9.0-draft` release and may change; `git fetch upstream` brings in updates.
