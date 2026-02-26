# Cursor/GPT Prompt: Build + Validate a Deployable Challengers Moneyline Strategy

You are a quantitative betting analyst and applied ML engineer working inside this repo. Your job is to **design, backtest, and write a deployable spec** for a **Valorant Challengers (Tier 2)** pre-match moneyline strategy using historical Thunderpick decimal odds from VLR.gg stored in SQLite.

You must **inspect the dataset directly** using the provided scripts and codebase. Do **not** guess. If something is missing, add code to measure it.

**Primary harness:** `scripts/challengers_analytics.py` — run this first. It produces `docs/CHALLENGERS_STRATEGY_SPEC.md` and prints the full analysis pipeline.

---

## 0) Goal

Find a **simple, implementable** strategy for Challengers moneylines that shows **repeatable out-of-sample edge** (or conclude no edge exists yet). If you find an edge, deliver:

1. **CHALLENGERS_STRATEGY_SPEC.md** (deployable rules)
2. **Backtest results with walk-forward splits**
3. **Monitoring + risk controls**
4. (Optional) a **bet log exporter** like the Tier 1 workflow

If no profitable strategy is found, say so explicitly and recommend next steps (more data, extra features, better market selection, etc.).

---

## 1) Data + Filtering Requirements (must follow)

**Use only matches that satisfy all:**

* completed match (`winner` set)
* both `team1_odds` AND `team2_odds` present
* no fabricated odds
* exclude odds ≈ 1.00 bug
* favorite definition = side with **lower** decimal odds; if odds are equal (or nearly equal), define a skip rule

**Challengers filter:**
Include events where event_name contains any of:

* `challengers`
* `ascension`
* `national competition`

(Keep the filter centralized and consistent across scripts.)

### Data we already have

**Full Challengers coverage (67 events)** via `populate_moneyline.py --challengers-only`. Current usable matches: ~700+ (Americas + EMEA; Pacific/China as populate completes).

- **Americas:** NA Qualifiers, Stage 1/2/3, Americas Ascension, LATAM North/South ACE (Splits 1–3), LATAM Regional Playoffs, Brazil (Splits 1–3)
- **EMEA:** EMEA Ascension, DACH, France, Spain, Italy, Portugal, Türkiye, East Surge, Northern Europe Polaris, MENA Resilience, MENA Regional Playoffs
- **Pacific:** Pacific Ascension, Korea, Japan, Oceania, Taiwan/Hong Kong, Thailand, Malaysia/Singapore, Philippines, Vietnam, Indonesia, South Asia, Southeast Asia
- **China:** China Ascension, China National Competition Season 2

---

## 2) What we've learned (recent research — read CHALLENGERS_STRATEGY_SPEC.md)

### Rejected / do not repeat

* **Absolute overround thresholds (e.g. ov ≤ 1.05):** The overround filter is a near-degenerate selector. 85%+ of bets land at ov≈1.05; ov≤1.045 gives n=0; ov≤1.055 collapses ROI to negative. This is a rounding/selection artifact, not a stable edge. **Do not use absolute overround cutoffs.**

* **"Always bet dogs":** Not supported. Flat B_dog ROI is negative; event-blocked median is negative.

* **Ou band [3.25, 5.00] with no ov filter:** ROI negative; permutation test (shuffle outcomes within event) shows p≈0.5 — not distinguishable from random.

### What *is* supported (structure only)

* **Ou [2.50, 3.25) is consistently bad** — avoid this band.
* **Ascension behaves opposite to Regular** — treat separately; do not mix.
* **Ridge logistic + EV gate (walk-forward OOS):** Tested; negative. Pre-match moneylines appear efficient with current features.

### Robustness checks you must run

* **Wilson CI on hit rate** vs break-even (1/avg_odds) — CI must clear break-even to claim edge.
* **Placebo bands** — adjacent Ou bands (e.g. [2.50, 3.25), [5.00, 7.50]) should stay weak if v0 is a real pocket.
* **Permutation test** — shuffle outcomes within event; if observed ROI is not extreme vs null, it's noise.
* **Overround rounding atoms** — print top 10 overround values; if one dominates, suspect data artifact.
* **OV cutoff sweep** — if strategy only works at exactly one cutoff (e.g. 1.05), it's suspicious.

### Graduation criteria (before any real sizing)

* n_events ≥ 10, n_bets ≥ 200
* median event ROI ≥ 0%, % events positive > 50–60%
* Wilson CI on hit rate clears break-even
* **Freeze the rule** — do not tweak thresholds until graduation.

---

## 3) Required Analyses (you must compute these)

### 3.1 Dataset inventory

Print:

* total challenger matches (raw)
* usable matches after cleaning
* usable matches by **region**
* usable matches by **tier detail** (Stage vs Qualifier vs Ascension vs other)
* % matches with near-even odds (|Of − Ou| ≤ 0.05)

### 3.2 Market stats

Compute and print overall + by region/tier:

* mean/median Of, Ou
* mean/median overround
* distribution of p_fair (buckets)

### 3.3 Calibration + drift

For favorites:

* per-match calibration error: mean(outcome − p_fair)
* vig effect: mean(p_raw − p_fair)
* calibration by p_fair buckets (or Of buckets), with Wilson or Beta CI
* drift by time (at least by month or by stage if possible; otherwise by event order)

### 3.4 Baselines (must report)

At minimum:

* A_always_fav (flat 1u)
* B_always_dog (flat 1u)
* ROI, n_bets, hit rate, max drawdown
* bootstrap ROI CI (block bootstrap by event) for the baseline(s)
* B_dog by Ou bucket ([2.00,2.50), [2.50,3.25), [3.25,5.00), [5.00+])
* event-blocked B_dog (median event ROI, % positive, worst)

### 3.5 Robustness (must run for any candidate)

* Wilson 95% CI on hit rate vs break-even (1/avg_odds)
* Placebo bands (adjacent Ou bands with same filters)
* Permutation test (shuffle outcomes within event, 1000 reps)
* Overround rounding atoms (top 10 values)
* OV cutoff sweep (e.g. 1.045, 1.05, 1.055) — strategy should not collapse at small looseness

---

## 4) Strategy Search Space (keep it parsimonious)

You may propose strategies using only features derivable from the DB fields:

* region (from event_name parsing)
* tier detail (Stage / Qualifier / Ascension / Other)
* p_fair (de-vig favorite probability)
* Of / Ou
* overround (use as **soft** signal, not hard cutoff)
* near-even filter

### Do NOT use

* Absolute overround cutoffs (e.g. ov ≤ 1.05) — proven artifact
* Ou band [2.50, 3.25) — consistently bad

### Allowed strategy forms (examples)

Pick a small set of candidates; do NOT brute force huge grids.

**Market selection filters**

* certain regions only
* certain tiers only (e.g., Qualifiers only)
* **percentile-based** overround (e.g. bottom 20% overround *within* Ou band) — not absolute cutoff

**Odds band rules**

* bet favorite only when `p_fair ∈ [a, b]`
* bet dog only when `p_fair ∈ [c, d]` (i.e., when dog is "live" but not a longshot)
* exclude heavy favorites or extreme dogs
* Of_min guard (avoid ultra-short favorites)
* skip near-equal odds

**Model-assisted (preferred over threshold search)**

* **Ridge logistic regression** on p_fair + log(Of), log(Ou), overround, tier/region/Ou-bin one-hots, p_fair×Ascension
* EV threshold rule: EV_fav = p×(Of−1) − (1−p), EV_dog = (1−p)×(Ou−1) − p; bet only if EV ≥ ev_min
* Walk-forward: train on early 70% events, test on last 30%

**Optional calibration-assisted**

* isotonic calibration of p_fair → p_true using deterministic PAV (like Tier 1)
* If using isotonic: trained only on train split, applied only on test split, deterministic PAV

---

## 5) Backtest Protocol (must be rigorous)

### 5.1 Splits

Use **time-based / year-based / event-order** splits. Prioritize:

* Train: early 2024 → Test: late 2024
* Or train on first X% of events → test on last (by event ordering)

If you have 2025+ data, do walk-forward by year.

### 5.2 Metrics (must report)

For each strategy:

* ROI = sum(profit)/sum(stake)
* n_bets
* hit rate
* avg/median odds taken
* max drawdown
* longest losing streak
* event-blocked validation:

  * median event ROI
  * % events positive
  * worst event ROI

### 5.3 Uncertainty

For top candidate(s):

* block bootstrap by event on test set (fixed strategy definition)
* report ROI p5/p50/p95 and drawdown p5/p50/p95

### 5.4 Overfitting / robustness checks

* EV threshold sweep (if using EV strategy) to show plateau not spike
* sensitivity check: small ± adjustments to p_fair bounds shouldn't flip results wildly
* **permutation test:** shuffle outcomes within event; observed ROI should be extreme vs null
* **placebo bands:** adjacent Ou bands should stay weak if your band is a real pocket
* **OV cutoff sweep:** if strategy only works at one exact cutoff, treat as artifact

---

## 6) Output Deliverables (must produce)

### 6.1 Strategy spec markdown

Create `docs/CHALLENGERS_STRATEGY_SPEC.md` similar to Tier 1 spec, including:

* Executive summary
* Strategy v1 (final)
* Quick reference table:

  * Universe
  * Bet side rule
  * Entry criteria
  * Stake sizing
  * Caps
  * No-bet zones
  * Kill switch
  * Review cadence
* Monitoring checklist (monthly review)
* What to avoid / invalidate
* Reproducibility (exact command(s) to run)
* Disclaimer

### 6.2 Code changes (if needed)

If you implement a new strategy function, add:

* `run_challengers_strategy_v1(...)`
* optional `generate_challengers_bet_log(...)` and `--betlog` CLI
* reuse / mirror Tier 1 infrastructure where appropriate

### 6.3 If no edge found

Write a brief "negative result" spec:

* no profitable strategy found under constraints
* show top candidates + OOS stats
* recommend next steps (in order of likelihood to help):

  1. **CLV / odds snapshots** — pre-match moneylines appear efficient; line-movement (stale-line) data may be needed
  2. more data (2025+ challengers, more events per region)
  3. additional features (team ELO from past results, roster stability proxy, map pool)

---

## 7) Concrete steps you should take right now (do these in order)

1. Run the main harness:

   * `python scripts/challengers_analytics.py` — produces full pipeline + spec
   * `python scripts/challengers_underdog_test.py` — underdog vs favorite comparison

2. Read `docs/CHALLENGERS_STRATEGY_SPEC.md` — it reflects current research state.

3. If extending the pipeline, add to `challengers_analytics.py`:

   * new strategy functions (e.g. `run_ev_model_strategy`, `run_ou_band_ov_percentile`)
   * robustness checks (permutation, placebo bands, Wilson CI, OV sweep)
   * wire results into `write_spec()` for the spec markdown

4. Report results in a structured way:

   * Baselines
   * Best candidate(s)
   * Robustness checks (permutation p-value, placebo bands, Wilson CI vs break-even)
   * Final recommended v1 rule (or negative result with next steps)

---

## 8) Constraints / Style

* No subjective judgment per match
* Prefer a **single simple rule** over a complex model
* **Avoid "strategy that only works in one tiny slice"** — e.g. ov≤1.05 was a razor-thin overround atom
* If sample sizes are small, say so, and lean conservative
* Don't claim profitability unless OOS + event-blocked + bootstrap support it
* **Wilson CI on hit rate must clear break-even** — necessary but not sufficient at small n
* **Freeze the rule** until graduation (≥200 bets, ≥10 events); don't tweak after every small sample

---

## Starter / reference

The main pipeline uses `scripts/moneyline_analytics.load_raw_data()`, `clean_data()`, `compute_vig_and_pfair()`, then filters by `is_challengers()`. See `scripts/challengers_analytics.py` for the full flow.

```bash
python scripts/challengers_analytics.py   # full pipeline → spec
python scripts/challengers_underdog_test.py   # underdog vs favorite
```
