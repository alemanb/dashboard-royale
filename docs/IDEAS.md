# Ideas & Decisions Log

A running list of ideas we're batting around. Move an item to **Decided** once we commit to it, and note why.

## Open questions

- [ ] **Dashboard tool:** Streamlit / Plotly Dash (Python, easy to host) vs. Tableau Public / Power BI vs. a static HTML page (see `../example-dashboard.html`)
- [ ] **Forecast model:** weekday-average baseline vs. something stronger (e.g. weekday + event/holiday effects, gradient boosting) for daily floor coin-in
- [ ] **Which decision the forecast drives:** technician staffing? promotion weekend timing?
- [ ] **Lean scope:** budget-feasibility checker only, or also ranking and formula certificates?
- [ ] **Originality angle:** what unexpected finding can we chase?

## Ideas

- **Lean 4 as an output checker.** Python computes, exports integer-cent JSON, and Lean proves the budget plan is feasible and the ranking matches its stated metric. A possible "formally verified recommendations" line for the video.

## Decided

- **Analysis in Python + DuckDB**, querying Parquet directly. *Why:* the large tables (1.3M rows) need it, and the rest of the stack is Python.
- **Repo is a fork** of `tamu-datathon-org/dashboard-royale`. *Why:* the data is a `0.9.0-draft` release and may change; `git fetch upstream` brings in updates.
