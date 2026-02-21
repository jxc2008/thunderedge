# Challengers (Tier 2) Pre-Match Moneyline Strategy — Spec

**Generated:** 2026-02-18 02:58
**Data:** Thunderpick decimal odds from VLR.gg, Challengers 2024.
**Usable matches:** 733

---

## Executive Summary

- **Status: Not ready for real staking.** With n_events=26 and event-blocked negativity, any edge is unconfirmed.
- **v0 (ov≤1.05) REJECTED:** The overround filter is a near-degenerate selector — 87% of v0 bets at ov≈1.05; ov≤1.055 collapses ROI to negative. Use percentile-based filters or no ov rule.
- **New hypothesis:** If any dog edge exists, it's in Ou [3.25, 5.00] (or 3.25–7.50) and is *not* explained by a stable vig threshold. Ou [2.50, 3.25) is consistently bad.
- **Segmentation findings:** Ascension behaves opposite to Regular; Ou 2.50–3.25 is the worst dog bucket.

### Definitions used in this report

- ROI = sum(profit)/sum(stake)
- A_fav / B_dog = unconditional baseline bets on every usable match
- Filters (e.g., overround ≤ 1.05) apply **on top of** baseline unless explicitly stated as "Strategy v0 filter"
- Event-blocked ROI computed over events with ≥1 bet under that rule
- ROI_implied = hit_rate × avg_odds − 1 is an **approximation** (assumes flat 1u stakes, loss = −1, win profit = odds−1)

---

## 1) Negative Result for Deployable v1

**Do not deploy** a real-money Challengers strategy with current data.

| Check | Result |
|-------|--------|
| Event-blocked B_dog | median_event_roi -25.7%, pct_positive 19%, worst -100.0% |
| n_events | 26 |
| Bootstrap B_dog | ROI p5/p50/p95 = -29.3% / -22.8% / -15.2% |

Conclusion: Edge is not broad. One global Challengers rule does not exist.

*Worst event ROI often from small events (worst had n=3 bets); one bad bet can swing event ROI sharply.*

---

## 2) What We Learned (Segmentation)

### Ascension is a different market

| Bucket | n | A_fav ROI | B_dog ROI |
|--------|---|-----------|-----------|
| Regular (excl Ascension) | 686 | 2.7% | -24.8% |
| Ascension | 47 | -12.0% | 0.6% |

Treat Ascension separately. Do not mix with Regular until you have enough events in each.
Overall A_fav 1.7% is a mix weighted by counts (Regular n=686, Ascension n=47).

### Dog profitability is not "dogs in general"

| Ou band | n | ROI |
|--------|---|-----|
| [2.00, 2.50) | 216 | -11.7% |
| [2.50, 3.25) | 198 | -20.9% |
| [3.25, 5.00) | 144 | -24.4% |
| [5.00, 999.00) | 142 | -41.1% |

If there's anything real, it's about **which dogs** — mid dogs (Ou 3.25–5.00).

### Vig: baseline vs conditional v0

**(i) Baseline B_dog + overround filter only (no Ou band)**

| Filter | n | ROI |
|--------|---|-----|
| overround ≤ 1.05 | 326 | -8.1% |
| overround ≤ 1.07 | 733 | -23.2% |

**(ii) Strategy v0 (ov≤1.05 + Ou∈[3.25,5.00])**

| Rule | n | ROI |
|------|---|-----|
| v0 (all) | 62 | 34.5% |
| v0a (Regular only) | 57 | 30.9% |
| v0b (Ascension only) | 5 | 76.0% |

**v0 (all) diagnostics:** total_profit=21.4u, avg_odds=3.94, hit=33.9%, Wilson 95% CI=[23.3%, 46.3%], break-even rate=25.4%. top_wins=[3.8, 3.8, 3.8], top_losses=[-1, -1, -1]. EV_sanity (approx for flat 1u): ROI_implied=33.3% (actual 34.5%).

**v0 event distribution:** median_bets_per_event=2, max_bets_in_event=6, pct_from_top_event=10%.

**v0 event-level hit vs break-even:** (hit − 1/avg_odds in pp; more interpretable than ROI at small n)

| Event | n | hit% | avg_odds | hit−be (pp) |
|-------|---|------|----------|-------------|
| Challengers League 2024 Spain Rising: Sp | 1 | 100.0 | 4.00 | +75.0 |
| Challengers League 2024 DACH Evolution:  | 4 | 75.0 | 3.60 | +47.3 |
| Gamers Club Challengers League 2024 Braz | 3 | 66.7 | 4.61 | +45.0 |
| Champions Tour 2024 Americas: Ascension | 4 | 50.0 | 4.51 | +27.8 |
| Challengers League 2024 LATAM North ACE: | 2 | 50.0 | 4.40 | +27.3 |
| Challengers League 2024 North America: S | 2 | 50.0 | 3.71 | +23.0 |
| Challengers League 2024 Portugal Tempest | 2 | 50.0 | 3.65 | +22.6 |
| Challengers League 2024 North America: S | 2 | 50.0 | 3.46 | +21.1 |
| Challengers League 2024 Portugal Tempest | 5 | 40.0 | 3.83 | +13.9 |
| Challengers League 2024 North America: S | 5 | 40.0 | 3.61 | +12.3 |
| Challengers League 2024 DACH Evolution:  | 3 | 33.3 | 4.18 | +9.4 |
| Challengers League 2024 Spain Rising: Sp | 6 | 33.3 | 4.18 | +9.4 |


v0 adds Ou band to isolate mid dogs; baseline ov-filter mixes all dog bands (no Ou filter).

**Conclusion:** The v0 edge was entirely from the ov filter; Ou band alone shows no edge (permutation p≈0.5).

**Placebo bands (same ov≤1.05):** Ou [2.50, 3.25) n=70 ROI=-40.0%; Ou [5.00, 7.50) n=40 ROI=-33.5%. If v0 strong and adjacent weak, evidence of real pocket.

**v0 overround sanity:** mean=1.0496, n near [1.049,1.050]=54/62.

**Overround rounding atoms (top 3):** ov=1.0501 n=120, ov=1.0500 n=119, ov=1.0499 n=68.

**Ou [3.25,5.00] NO overround:** n=144 ROI=-24.4%, event-blocked median=-37.4% pct_positive=33%. The v0 'edge' was entirely from the ov filter.

**Permutation test (shuffle outcomes within event):** observed ROI=-24.4%, null p5/p50/p95=-25.6%/-23.1%/-21.0%, p-value=0.821. Not distinguishable from random.

**Ov-percentile (bottom X% within Ou band):** 10% n=14 ROI=305.7%, 20% n=28 ROI=126.4%, 30% n=43 ROI=47.4%.


**Edge model (ridge logistic + EV gate, walk-forward OOS):** EV>=0.00 n=171 ROI=-11.5%, EV>=0.01 n=144 ROI=-17.6%, EV>=0.02 n=128 ROI=-21.3%.
Event-blocked (EV>=0.01): median=-22.1% pct_positive=25%.


---

## 3) v0 REJECTED + New v0 Candidate

### v0 (ov≤1.05 + Ou∈[3.25,5.00]) — REJECTED

The apparent edge is not robust. The overround filter acts as a near-degenerate selector: 85%+ of v0 bets are in [1.049, 1.050]; ov≤1.045 gives n=0; ov≤1.055 collapses ROI to negative. This suggests a rounding/selection artifact, not a stable market inefficiency.

**Do not use absolute overround thresholds.** Revisit using percentile-based filters after full populate.

### New v0 candidate: Ou band only (no ov rule)

| Rule | Value |
|------|-------|
| **Universe** | Challengers matches with both odds + winner matched |
| **Market filter** | None (or optional: bottom 20% overround *within* Ou band) |
| **Bet side** | Underdog |
| **Odds band** | Ou ∈ [3.25, 5.00] |
| **Exclude** | Ou ∈ [2.50, 3.25) (known bad) |
| **Stake** | 0.25u flat |
| **Caps** | 1u/day, 1u/event |
| **Kill switch** | Stop if drawdown > 4u or ROI(last 30) < -5% |
| **Goal** | Validate across ≥10 events and ≥200 bets; event-breadth (median hit−BE > 0, % positive > 60%) |

Ou band [3.25, 5.00] with no ov filter shows ROI≈-24.4% — not distinguishable from null (permutation p≈0.82). Percentile filters may cherry-pick noise at small n. Revisit after full populate.

---

## 4) Acceptance Criteria: Graduate v0 → v1

Before upgrading to deployable v1, **all** must hold: n_events ≥ 10, n_bets ≥ 200, median event ROI ≥ 0%, % events positive > 50–60%, bootstrap p5 not wildly negative, Wilson CI on hit rate must clear break-even, overround matches not clustered in 1–2 events. First graduation check: event-breadth — median event hit−BE positive and % events positive > ~60%.

---

## 5) Post-Populate Validation

For each region and tier: apply v0 filter, print ROI, n_bets, median event ROI, % events positive, bootstrap CI. Check overround clustering (matches per event with ov ≤ 1.05).

---

## 6) Overround Clustering (Current)

Matches with overround ≤ 1.05: 326 across 26 events.
- Challengers League 2024 Spain Rising: Split 1: 28 matches
- Gamers Club Challengers League 2024 Brazil: Split : 24 matches
- Challengers League 2024 Italy Rinascimento: Split : 24 matches
- Challengers League 2024 Portugal Tempest: Split 2: 20 matches
- Challengers League 2024 DACH Evolution: Split 1: 19 matches
- Challengers 2024 Spain Rising: Consolidation: 18 matches
- Challengers League 2024 Italy Rinascimento: Split : 18 matches
- Challengers League 2024 North America: Stage 2: 16 matches

---

## Baselines

| Strategy | ROI | n_bets | hit_rate | max_dd |
|----------|-----|--------|----------|--------|
| A_always_fav | 1.7% | 733 | 73.1% | 14.83 |
| B_always_dog | -23.2% | 733 | 26.9% | 175.26 |

---

## Reproducibility

```bash
python scripts/challengers_analytics.py
python scripts/challengers_underdog_test.py
```

---

## Disclaimer

For educational and prototyping only. Not financial or betting advice. Check local laws.
