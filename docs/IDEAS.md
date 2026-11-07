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
- **The *lucky* tail is too fat, and it's organized by game** ([`Q1.md`](Q1.md#finding-4--a-lead-we-did-not-expect-the-lucky-tail-is-too-fat)): 9 machines above z = +2.5 where chance predicts 2. Platinum Reels keeps 10.6% against a published 10.0% (mean z +0.54, 2.7 standard errors); Neon Nights +0.32; Comet Cash runs *low* at −0.72 (3.5 s.e.). Is the configured RTP slightly off the published one? Does bet-size mix interact with the pay table? Testable with `machine_hour` bet distributions or by inspecting one machine per game. Not an accusation; a pattern to explain.
- **Ridgeline: are its machines older?** 56% of faults from 30% of machines. If `install_date` explains it, the fix is replacement of the oldest units rather than preventive maintenance across the brand. Check in Q3.
- **How much of the Back Forty's $1.26M theo gap is recoverable?** Moving machines redistributes demand. The honest estimate needs Q2 (where demand went) plus `floor_walkways` (is the Back Forty reachable?). Needed before pricing any move/signage action in Q6.
- ~~Ten machines below z = −2.5 where chance predicts two~~ resolved: an artifact of the variance formula; with each machine's own variance the count matches chance, and only M-1158 remains ([`DECISIONS.md` D7](DECISIONS.md)).

## Ideas

- **"Verified ✓" panel** in the dashboard: each recommendation links to the Lean check that passed, with the certificate values shown.
- **"We tried the fashionable thing and it lost"** as a communication row: Chronos-Bolt vs. a weekday average, with the explanation that 150 data points can't feed 48M parameters.
- **Rolling CV as the validation panel**: show the four folds, not one number. It answers the judges' "find how the model was validated" test directly and shows the single-holdout reversal honestly.
