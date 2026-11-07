# Ideas & Open Questions

A running list of ideas we're batting around. Once something is settled it moves to [`DECISIONS.md`](DECISIONS.md) with the reasoning.

## Open questions

- [ ] **Dashboard tool:** Streamlit / Plotly Dash (Python, easy to host, can refit AutoETS live when a judge changes the period) vs. Tableau Public / Power BI vs. a static HTML page (see `../example-dashboard.html`)
- [ ] **Forecast → decision link:** which action does the coin-in forecast actually decide? Candidates: which shift gets the added technician; which weekend gets the promotion.
- [ ] **Lean decision rule:** should Lean *choose* the $100K plan from the inputs (stronger, more work) or only *verify* a plan we pick (fits the time better)?
- [ ] **Originality angle:** what unexpected, reproducible finding can we chase?
- [ ] **Prediction intervals** from AutoETS (`level=[80, 95]`): needed for the uncertainty criterion; not yet produced.

## Leads from the data

- **The un-announced Locals Appreciation Week (Jun 9–15) was not harder to forecast than other days** (MSTL error $54K inside vs. $57K outside on the May 1 holdout). Did the promotion move coin-in at all? Or did it shift something else (comps, food & drink, carded share)? Worth a Q2/Q5 look.
- **Ten machines sit below z = −2.5 where chance predicts about two** (see `analysis/00_demo_stats_and_model.py`). The excess is where the real Q1 story is. M-1158 (z = −5.2) is the leading leak candidate; M-5076's tiny theo suggests a short time on the floor.

## Ideas

- **"Verified ✓" panel** in the dashboard: each recommendation links to the Lean check that passed, with the certificate values shown.
- **"We tried the fashionable thing and it lost"** as a communication row: Chronos-Bolt vs. a weekday average, with the explanation that 150 data points can't feed 48M parameters.
- **Rolling CV as the validation panel**: show the four folds, not one number. It answers the judges' "find how the model was validated" test directly and shows the single-holdout reversal honestly.
