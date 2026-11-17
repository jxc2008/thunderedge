# VALORANT match-market historical price sources: survey

Survey date: 2026-11-17. Survey only: metadata plus 3 sample matches per source. Raw samples are in `raw/`, scripts are `*.py` in this folder, and every request is logged in `req_log.txt` (the OddsPapi key is redacted as `<KEY>`; a grep confirmed the key string is not in any file here).

The same three tier-1 matches were sampled on every source so the results can be compared:

| Match | Kalshi event | Polymarket slug | OddsPapi fixtureId |
|---|---|---|---|
| Paper Rex vs Leviatán, Masters London 2026 Grand Final (2026-06-21) | KXVALORANTGAME-26JUN210900LEVPR | val-pr1-lev1-2026-06-21 | pn619050831632045608 |
| Cloud9 vs Evil Geniuses, VCT Americas Stage 2 (2026-08-17 UTC) | KXVALORANTGAME-26AUG162000EGC9 | val-c9-eg2-2026-08-16 | pn619022591634031316 |
| G2 vs Paper Rex, VCT Champions 2026 Group C (2026-09-29) | KXVALORANTGAME-26SEP290500G2PR | val-g21-pr1-2026-09-29 | pn619018531637281632 |

The sources disagree on start times. For PRX–LEV, the Kalshi ticker gives 09:00 ET (13:00Z), Polymarket's `startTime` is 14:30Z, and OddsPapi's `trueStartTime` is 13:03Z. For C9–EG they give 00:00Z, 01:00Z and 00:42Z (OddsPapi `startTime`). For pre-match windows, each source's own start time is used. A real study should use one external start time (for example vlr.gg or OddsPapi `trueStartTime`).

## Coverage table

| Source | Markets / coverage | Earliest date | Seasons covered | Granularity | Pre-match volume (3 samples) | Access / terms |
|---|---|---|---|---|---|---|
| **Kalshi** KXVALORANTGAME | 3,567 settled markets in 1,783 events: 3,117 from `/historical/markets` and 506 from live `/markets?status=settled`, with 56 overlapping. About 70 tournaments, from tier-1 VCT through VCL/Challengers, Game Changers and third-party events | 2025-09-24 (Champions 2025 Paris: 8 events, non-standard tickers `KXVALORANTGAME-25-…`) | Champions 2025 only, then continuous from Jan 2026 to now. 2026Q1 293 events, Q2 675, Q3 609, Q4 (to Nov 17) 198. **No markets in Oct–Dec 2025** | Every trade, with microsecond timestamps (`/historical/trades` or `/markets/trades`). Candles at 1 min, 60 min or 1440 min, with OHLC for trade price, yes_bid and yes_ask, plus volume and open interest (OI) | Contracts traded pre-start: PRX–LEV 73,059 (644 trades), C9–EG 10,482 (157 trades), G2–PRX 91,744 (444 trades). Markets open about 1–3 days before the match. About 85–98% of total volume trades in-play | Public market data, no auth. Data older than the cutoff (`market_settled_ts`/`trades_created_ts` = 2026-09-18) must come from `/historical/*`. Hit one HTTP 429 at about 1 req/s. ToS not reviewed |
| **Polymarket** (Gamma, CLOB, Data API v2) | 2,996 closed events with `tag_slug=valorant`. In the first 1,500 (created before 2026-04-20), about 90% are single matches (moneyline plus map markets). The rest are futures and props | First match market: 2025-08-20 (DRX Academy vs FEARX). First event of any kind: Jan 2025 (futures) | By event `endDate`: 2025Q1 1, Q2 1, Q3 18, Q4 228; 2026Q1 946, Q2 918, Q3 605, Q4 240 (includes non-match events) | Data API v2 `/v2/trades`: every taker fill, 1 s timestamps, cursor pagination, no time filter for market queries (newest first). CLOB `prices-history` with an explicit `startTs/endTs` and `fidelity=1`: one sampled price per minute | Pre-48 h taker trades: C9–EG 456 trades, $97k USDC; G2–PRX 851 trades, $291k USDC. PRX–LEV: not reached (the newest 5,000 trades were all in-play). Moneyline volumes: $0.44M–$1.9M per match, much larger than Kalshi's pre-match | Public, no auth. **Data API v1 is retired** (`/trades` returns HTTP 410) and v2 must be used. `prices-history?interval=max` returned **empty** for all 3 resolved markets. ToS not reviewed |
| **OddsPapi** (free key) | Sport 61 "ESport Valorant": 532 tournaments listed, most of them legacy 2021-era IDs. Live fixture data appears under new IDs, e.g. Champions Tour Americas, EMEA, Pacific and China, Masters London, Champions, and many Challengers leagues. **Tier-2 Challengers is included** | Fixtures: about 2025-07-28. **Historical odds: Jan 2026 only** (docs say this; a 2025-10-04 Champions fixture returned 404 "No historical odds found") | Fixtures 2025H2 and 2026. Odds history 2026 only. No fixtures in 2023, 2024 or June 2025 windows | Event-driven price-change log with sub-second `createdAt` timestamps. Pinnacle median gap between updates is 40–137 s pre-match (minimum 0.08 s). Covers pre-match and in-play | Pinnacle pre-match updates: 183, 91 and 174, starting 17–28 h before start. Stake: 23, 18 and 56. Bet365: 12 and 108. Books publish no volume. Pinnacle's `limit` field gives the max stake | Free plan is 250 billable requests per month, resetting on the 1st (26 used). `/historical-odds` is not billable but has a 5 s cooldown and takes at most 3 bookmakers per call. **Thunderpick is restricted on this plan (HTTP 403).** Terms forbid redistributing the data "as a standalone product" |

## 1. Kalshi

### 1a. Market listing
- Docs: `https://docs.kalshi.com/llms.txt` and `getting_started/historical_data.md`. Kalshi now splits data into a live tier and a historical tier. `GET /historical/cutoff` returned:
  `{"market_settled_ts":"2026-09-18T00:00:00Z","trades_created_ts":"2026-09-18T00:00:00Z","orders_updated_ts":"2026-11-03T00:00:00Z","market_positions_last_updated_ts":"2026-09-18T00:00:00Z"}`.
  - Markets or candlesticks settled before the cutoff are served only by `/historical/markets` and `/historical/markets/{ticker}/candlesticks`.
  - Trades before the cutoff are served only by `/historical/trades`.
  - Events and series stay available on their normal endpoints.
- `GET /markets?series_ticker=KXVALORANTGAME&status=settled&limit=1000` returned 506 markets on 1 page. All are `finalized` and settled after the cutoff.
- `GET /historical/markets?series_ticker=KXVALORANTGAME&limit=1000` returned 3,117 markets over 4 pages (one extra request got HTTP 429 and the paging was re-run more slowly).
- The union is 3,567 markets in 1,783 events. Results: 1,757 yes, 1,758 no and 52 `scalar` (presumably voided or cancelled; inferred).
- Event dates come from the ticker (`YYMONDDHHMM` in US Eastern time; the rules text says "3:30 AM EST"). Where a ticker has no date, `open_time` is used.
  - Earliest: `KXVALORANTGAME-25` (Fnatic vs DRX), with open_time 2025-09-24T14:00Z. Champions 2025 has 8 events. The 2025 tickers do not follow the later format (`KXVALORANTGAME-25-DRXG2-G2`).
  - Latest: 2026-11-17 (China National Tournament).
  - Per quarter: 2025Q3 8, 2025Q4 0, 2026Q1 293, 2026Q2 675, 2026Q3 609, 2026Q4 198.
  - Per month (markets): Jan 122, Feb 201, Mar 264, Apr 610, May 452, Jun 288, Jul 560, Aug 434, Sep 224, Oct 182, Nov 214.
- Per-market `volume_fp`: median 20,599 contracts, p90 150,034, max 882,900. 18 markets had zero volume.
- Event volume by tournament (contracts, both sides), top entries:

| Tournament | Events | Volume (contracts) |
|---|---|---|
| VCT Americas Stage 2 | 60 | 30.5M |
| VCT EMEA 2026 | 102 | 24.6M |
| VCT Champions 2026 | 34 | 22.5M |
| VCT Pacific | 103 | 12.8M |
| VCL North America | 122 | 12.5M |
| VCT Americas Stage 1 | 40 | 12.0M |
| Masters London | 24 | 11.1M |
| EWC 2026 | 29 | 8.4M |

  Masters Santiago, the Kickoffs, VCT China, Game Changers and many VCL leagues are also listed.
- The `occurrence_datetime` field is **not** the start time. It sits about 4 h after the ticker time (inferred: expected end).

### 1b. Price history for the 3 samples
Endpoints:
- Candles: `/historical/markets/{t}/candlesticks` for the two pre-cutoff markets and `/series/KXVALORANTGAME/markets/{t}/candlesticks` for G2–PRX, each called with `period_interval=1` over the window [start − 48 h, start + 6 h]. Allowed intervals are 1, 60 and 1440 min. At most 5,000 periods fit in one historical request.
- Trades: `/historical/trades` or `/markets/trades` with `ticker`, `min_ts=start-48h`, `max_ts=start` and `limit=1000`. One page was enough each time.

| Market (one side) | Market open | Start (ticker, UTC) | 1-min candles pre-start (with volume>0) | Pre-start trades / contracts | Trades in last 6 h | In-play candle volume | Total market volume |
|---|---|---|---|---|---|---|---|
| …LEVPR-PR | 06-20 16:37 | 06-21 13:00 | 807 (347) | 644 / 73,059 | 294 | 572,389 | 645,447 |
| …EGC9-EG | 08-15 04:05 | 08-17 00:00 | 377 (115) | 157 / 10,482 | 104 | 463,127 | 473,610 |
| …G2PR-G2 | 09-26 00:05 | 09-29 09:00 | 874 (283) | 444 / 91,744 | 229 | 614,844 | 708,948 |

- Candles are sparse: about 60% are 60 s apart and the rest have 120 s or 180 s gaps (minutes are skipped).
- Candle volume matches the trade sums exactly (73,058.51 vs 73,059).
- Each trade row has `created_time` (µs), `yes_price_dollars`, `count_fp` and `taker_side`.
- **The finest granularity is individual trades.** Bid/ask candles also give a 1-minute quote history.
- Pre-match volume is real but small next to in-play. It is roughly 10k–90k contracts (about $5k–$60k notional; inferred from prices).

## 2. Polymarket

### 2a. Market listing
- `GET gamma-api.polymarket.com/events?tag_slug=valorant&closed=true&order=startDate&ascending=true` caps pages at 100.
  - 15 pages (1,500 events, created up to 2026-04-20) were read. Paging stopped there to stay within the cap.
  - `GET /events/pagination?...&limit=1` gives `totalResults: 2996` closed events.
- Per-quarter counts came from `/events/pagination` with `end_date_min/max` (9 requests): 2024 0; 2025Q1 1, Q2 1, Q3 18, Q4 228; 2026Q1 946, Q2 918, Q3 605, Q4 240.
- In the 1,500 read:
  - 1,346 events are match-like ("X vs Y", 1–6 markets).
  - The earliest match market is `valorant-drx-academy-vs-fearx`, ending 2025-08-20. Older events (from Jan 2025) are futures such as `vct-2025-americas-kickoff-winner`.
  - 2026 matches by title: 268 tier-1 VCT (Kickoffs, regional leagues, Masters Santiago), 663 Challengers/VCL, 176 other.
  - Median tier-1 moneyline volume is about $76k (n=192).
- A match event has a `moneyline` market (BO3 or BO5 winner) and per-map "Map N Winner" markets. Fields include `gameStartTime`, `startTime`, `clobTokenIds` and `conditionId`.
- Sample events were found with `/events?tag_slug=valorant&closed=true&end_date_min/max` around each Kalshi date (3 requests):
  - val-pr1-lev1-2026-06-21: event $2.44M, moneyline $1.48M
  - val-c9-eg2-2026-08-16: event $0.67M, moneyline $0.44M
  - val-g21-pr1-2026-09-29: event $2.56M, moneyline $1.90M

### 2b. Price and trade history

**CLOB `prices-history`**
- `?market=<token>&interval=max&fidelity=1` returned `{"history": []}` for all 3 resolved markets.
- `?market=<token>&startTs=start-48h&endTs=start&fidelity=1` worked, with about 60 s spacing:

| Match | Points | First point | Distinct prices |
|---|---|---|---|
| PRX–LEV | 1,257 | 06-20 17:33Z | 18 |
| C9–EG | 2,406 | 08-15 08:54Z | 27 |
| G2–PRX | 2,880 | 09-27 09:00Z | 8 |

  These are sampled prices, not trades.

**Data API**
- `data-api.polymarket.com/trades?market=` returns **HTTP 410**: "Data API v1 has been retired". The v1→v2 migration doc says v1 retired on 2026-11-02.
- v2 is `GET /v2/trades?condition=<conditionId>&limit=1000` with `next_cursor` pagination. Its `start`/`end` window parameters work **only with `user=`**, so a market feed has to be paged from newest to oldest.
- The data includes wallet and profile fields. These were stripped from the saved samples.

| Match | Pages fetched | Reached pre-match? | Pre-48 h taker trades | Pre-48 h shares | Pre-48 h USDC | Last 6 h trades | In-play (fetched) |
|---|---|---|---|---|---|---|---|
| PRX–LEV | 5 (5,000 rows) | **No** (oldest row 15:51Z, all in-play) | n/a | n/a | n/a | n/a | 5,000 trades, $569k |
| C9–EG | 2 (complete) | Yes | 456 | 175,347 | $97,235 | 341 | 1,410 trades, $138k |
| G2–PRX | 5 | Yes | 851 | 585,191 | $290,674 | 418 | 4,080 trades, $688k |

- Granularity: individual fills (`timestamp` in seconds, price, size, side, outcome).
- `taker_only` defaults to true, so each fill appears once.
- Data API v2 also has `/v2/prices-history` with `bucket_seconds` from 60 to 86,400. It was not tested.

## 3. OddsPapi

### Public site and docs (oddspapi.io; 9 page requests, not blocked; robots.txt `Allow: /`)
- `https://oddspapi.io/llms.txt`:
  - "aggregates real-time and historical odds from 300+ bookmakers — including sharps (Pinnacle, Singbet, SBOBet)…"
  - Esports are listed. The quick-start names CS2, LoL and Dota explicitly.
  - "Historical Odds: Available on free tier".
- Free plan (homepage pricing strings): "Pre-game REST API", "Unlimited sports", "Historical data", "250 requests/month". Also: "The free quota resets on the 1st day of each month."
- Quota notes in the docs bundle (`https://oddspapi.io/us/docs`):
  - "1 Request = 1 call to a billable API endpoint, regardless of the response."
  - "`/v4/account` doesn't count against your quota. `/v4/historical-odds` doesn't count against your quota either, but you can't call it once the quota is used up."
- Historical endpoint (`https://oddspapi.io/us/docs/get-historical-odds`): `GET /v4/historical-odds?fixtureId=…&bookmakers=…`.
  - "Comma-separated list of bookmaker slugs (max 3)".
  - Each entry carries `createdAt` (µs ISO timestamp), `price`, `limit` (max stake) and `active`.
  - "Endpoint cooldown (rate limit): 5000ms". "**All historical odds data since January 2026 is available.**"
  - The docs state no fixed sampling granularity. Each entry is a recorded price change.
- `/v4/fixtures` (`https://oddspapi.io/us/docs/get-fixtures`):
  - Takes `tournamentId` or `participantId` alone, or `sportId` together with `from`/`to` less than 10 days apart.
  - Cooldown 2,000 ms. `/v4/tournaments` cooldown is 1,000 ms.
- **Terms** (`https://oddspapi.io/us/legal/terms`), quoted:
  - §3: "You may not resell, repackage, or redistribute our data as a standalone product." / "We may revoke your access if we detect any misuse or unauthorized distribution." / "If unsure about your use case, contact us…"
  - §4: "Your API key is personal and tied to your plan. Keep it secure and do not share it."
  - §6: "We monitor usage for abuse such as exceeding limits, sharing API keys, or scraping."
  - §2: "we do not guarantee accuracy or completeness."
  - The terms say nothing explicit about research use or local storage. Internal research use with stored copies looks allowed as long as the raw data is not redistributed as a standalone product (inferred, not stated).

### API with the user's key (33 requests to api.oddspapi.io; account shows `plan: free, request_limit: 250, request_count: 26` afterwards)

**3b. Coverage**
- `/v4/sports` lists sportId 61 `esport-valorant`.
- `/v4/tournaments?sportId=61` returned 532 tournaments, all with 0 future or upcoming fixtures right now:
  - 471 in category "Valorant", mostly legacy IDs such as "Champions Tour: NA Challengers 1".
  - 57 in category "Riot Games" (VCT Americas, EMEA, Pacific, China, Masters, Champions, about 18 Challengers leagues, Game Changers, Ascension…).
  - 4 others.
- Fixtures are actually filed under a third set of IDs. Fixture counts from `/v4/fixtures?tournamentId=`:

| ID | Tournament | Fixtures | Range | By quarter |
|---|---|---|---|---|
| 902259 | Champions Tour: Americas | 136 | 2025-08-01 → 2026-09-06 | 2025Q3 31, 2026Q2 44, 2026Q3 61 |
| 902257 | Champions Tour: EMEA | 143 | 2025-07-30 → 2026-08-30 | 2025Q3 31, 2026Q2 47, 2026Q3 65 |
| 902258 | Champions Tour: Pacific | 130 | 2025-08-01 → 2026-09-06 | 2025Q3 24, 2026Q2 43, 2026Q3 63 |
| 904888 | Champions Tour: China | 106 | 2026-04-04 → 2026-08-23 | 2026Q2 40, 2026Q3 66 |
| 905083 | Masters London | 28 | 2026-06-06 → 2026-06-21 | 2026Q2 28 |
| 901853 | Champions | 94 | 2025-09-12 → 2026-10-18 | 2025Q3 33, 2025Q4 6, 2026Q3 27, 2026Q4 28 |
| 902245 | Challengers Korea (tier-2) | 94 | 2025-07-28 → 2026-07-15 | 2025Q3 26, 2026Q1 28, 2026Q2 30, 2026Q3 10 |

  Kickoff 2026 fixtures sit under separate IDs (902379–902381, 904619).
- Older "Riot Games" IDs return almost nothing. 45415 VCT Americas returned only 6 fixtures (July 2025); 45419, 45417, 42847, 43433, 51836 and 45865 returned 404.
- `sportId=61` date windows:

| Window | Fixtures |
|---|---|
| 2026-06-12..21 | 33 (Masters London 18, Challengers Korea and LATAM) |
| 2026-08-08..17 | 66 |
| 2026-09-22..10-01 | 29 |
| 2026-01-20..29 | 109 (Kickoffs, Game Changers, 7 Challengers leagues) |
| 2025-09-25..10-04 | 31 |
| June 2023, June 2024, June 2025 | **404, no fixtures** |

- **There is no coverage for 2023 or 2024, and fixtures start around late July 2025.** Odds history is only available from Jan 2026.
- `hasOdds` was false and `statusId` mostly null on every past fixture, so these fields do not show whether odds history exists.

**3c. Bookmakers**
- `/v4/bookmakers` lists 323 books, including `pinnacle`, `pinnacle+5`, `pinnacle+30`, about 6 Pinnacle clones, `stake`, `bet365`, `1xbet`, `cloudbet`, `polymarket` and `kalshi`.
- **Thunderpick is listed** (`thunderpick.io`, liveOdds true) **but is not in the free subscription's bookmaker list** (348 entries, which do include `pinnacle`).
- `/v4/historical-odds?bookmakers=pinnacle,thunderpick.io` returned **HTTP 403** `RESTRICTED_ACCESS`: "Restricted bookmakers: thunderpick.io. You do not have access to these bookmakers."
- Bookmakers with Valorant odds history in the samples: pinnacle, stake and bet365. 1xbet returned nothing for PRX–LEV.
- Only market `611`/outcomes `611`,`612` (match winner) was returned. There were no map or handicap markets in the history.

**3d. Historical odds for the 3 samples** (`/v4/historical-odds`; start = OddsPapi `trueStartTime` or `startTime`)

| Fixture | Book | Entries (pre / in-play) | Pre-match price changes | First entry before start | Median gap pre-match | Min gap |
|---|---|---|---|---|---|---|
| PRX–LEV (start 13:03Z) | pinnacle | 183 / 0 | 171 | 17.1 h | 40 s | 0.08 s |
| | stake | 23 / 0 | 21 | 20.5 h | 23 min | 6.8 min |
| C9–EG (00:42Z) | pinnacle | 91 / 1,024 | 83 | 23.3 h | 137 s | 0.3 s |
| | stake | 18 / 56 | 16 | 40.4 h | 64 min | 6.5 min |
| | bet365 | 12 / 4 | 0 | 5.0 h | 45 min | 25 min |
| G2–PRX (09:08Z) | pinnacle | 174 / 1,353 | 159 | 27.5 h | 72 s | 0.3 s |
| | stake | 56 / 84 | 54 | 61.9 h | 15 min | 8 s |
| | bet365 | 108 / 8 | 10 | 59.6 h | 27 min | 3 min |

- Each entry is a recorded change, close to tick level for Pinnacle.
- In-play history is present for C9–EG and G2–PRX even on the free plan. PRX–LEV has no entries after 13:00:20Z.
- A 2025 fixture (DRX vs Fnatic, Champions 2025, 2025-10-04) returned 404 "No historical odds found". This matches the "since January 2026" statement.

## 4. Thunderpick vs Pinnacle lag

**Not run.** Both books must have historical Valorant odds, and Thunderpick is restricted on this key's free plan (403 above). Pinnacle history is available.

If Thunderpick access is obtained (paid plan), the planned method is:
1. Pull `/v4/historical-odds?fixtureId=…&bookmakers=pinnacle,thunderpick.io` (market 611) for up to about 10 tier-1 2026 fixtures. This is 1 non-billable call per fixture with a 5 s cooldown.
2. For each book, build a step function of the de-vigged home probability: p = (1/o1) / (1/o1 + 1/o2), using the latest active price of each outcome at each `createdAt`.
3. Keep only the pre-match part (before `trueStartTime`).
4. Find Pinnacle moves: from each anchor, the first time t₁ at which the de-vigged probability has moved at least 2 pp from the anchor's level. The move size is Δ = p(t₁) − p(anchor), and the anchor then resets to t₁.
5. For each move, Thunderpick's lag is the first time t ≥ t₁ − 60 s at which its de-vigged probability has moved at least |Δ|/2 in the same direction from its level at the anchor time. Moves where Thunderpick never follows before start are counted as "never followed" (censored).
6. Report the median and IQR of lag over matched moves, the number matched, and the number never followed. Keep the opposite-direction case separate.

## Request counts (by host)

| Host | Requests |
|---|---|
| docs.kalshi.com | 3 |
| api.elections.kalshi.com | 15 (incl. 1 HTTP 429) |
| gamma-api.polymarket.com | 28 |
| clob.polymarket.com | 6 |
| data-api.polymarket.com | 16 (3 × HTTP 410 on v1, 1 OpenAPI spec, 12 v2 trades) |
| docs.polymarket.com | 2 |
| oddspapi.io (public site/docs) | 9 |
| **Subtotal (non-OddsPapi API, cap 120)** | **79** |
| api.oddspapi.io (cap 60) | 33 (26 billable against the 250/month quota, per `/v4/account`) |
| **Total** | **112** |

Same-host sleep was ≥ 1.1 s, with 2.5 s and 5.5 s for OddsPapi cooldowns. User-Agent: `research-survey/0.1`. No sign-ups, and no personal data was sent.

## Not verified / caveats
- **Kalshi:** the ToS and market-data redistribution terms were not read. Start times come from tickers (scheduled start, ET), not actual start. The meaning of the 52 `scalar` results is inferred.
- **Polymarket:**
  - Event counts are for `tag_slug=valorant`. Match events from before Aug 2025 might exist under other tags (not checked).
  - Only the first 1,500 of 2,996 events were read in full. Per-quarter counts include futures and props.
  - Pre-match trades for PRX–LEV were not reached within 5 pages.
  - Polymarket ToS was not read.
- **OddsPapi:**
  - Full per-season fixture counts for all tournaments were not enumerated (sampled tournaments and windows only).
  - Fixture coverage before July 2025 was checked only with June windows.
  - Whether a paid plan unlocks Thunderpick history, and from which date, is not verified.
  - Whether the free plan truncates in-play history (PRX–LEV had none) is unknown.
  - Terms have no explicit clause on research or storage; the reading above is inferred.
