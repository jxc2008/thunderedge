# Always-on hosting for the odds logger: proposal (not deployed)

What has to run: `research/odds_logger.py` every 15 min. Each run is a ~10–60 s Python process
that polls vlr.gg (Thunderpick widget) and the public Kalshi API and appends to SQLite. Later,
the same box can run `valorant-pricing-model/scripts/shadow_quotes.py` and the pricing bot.

Measured load (this laptop, 2026-11-17, off-season):
- Data: ~1.1 MB of SQLite per 6 h (≈ 4–5 MB/day; ~30% is stored raw JSON/HTML).
- Requests: 1 vlr request + 2 Kalshi requests per poll, because no tier-1 VCT match is upcoming.

**In season the vlr load is much higher under the current cadence.** A match page is fetched
every poll inside 48 h of start and every 2 h within 7 days. During Kickoff, with ~6 matches
inside 48 h, that comes to ≈ 96 × (2 list pages + 6 match pages) + ~170 ≈ **900 vlr
requests/day**. Because of the page cap I'd tighten this before Kickoff:

| Window before start | Match-page cadence |
|---|---|
| T − 3 h to T | every poll |
| T − 48 h to T − 3 h | every 2 h |
| T − 7 d to T − 48 h | every 12 h |

That gives ≈ 300 requests/day, and keeps everything the pre-registration needs (T − 60 min and
the close). This is your call — see the questions at the end.

## Options

Prices were checked 2026-11-17 against third-party summaries and are not quotes; confirm them
on the providers' pages.

| | A. Small VPS + SQLite (recommended) | B. VPS → Supabase Postgres | C. GitHub Actions cron (*/15) |
|---|---|---|---|
| Monthly cost | ≈ €5–7: Hetzner CAX11 / CX23 class after the June 2026 price rise, + €0.50 IPv4. Backups ≈ $0 (Cloudflare R2 / Backblaze B2 free tiers) | VPS as A + Supabase free ($0) until 500 MB, then Pro $25 | Public repo: $0 runner minutes. Private repo: ~2,900 min/month (96 runs × ~1 min incl. setup) vs 2,000 free → small overage. Still needs a database (Supabase), because runners have no disk |
| Setup work | ~1 h: user, venv, cron, nightly backup, health ping. No code change | A + port writes to Postgres (≈ 1–2 h); schema already simple | Workflow file + secrets + Postgres port |
| Timing fidelity | cron on the minute | same as A | **No SLA.** Delays of 5–30 min are common under load and runs are sometimes skipped — bad for the T − 60 min bet price and the closing price |
| Storage headroom | 40 GB disk ≈ years at ~5–15 MB/day | Free 500 MB fills in ≈ 2–4 months at the measured rate (keeping raw HTML/JSON shortens that) → $25/month Pro | same as B |
| Public-repo risk | none | none | Workflow logs on a public repo are public, and committing data back would put raw scraped data in the public repo (which you've ruled out) → must be a private repo |

## Failure modes and mitigations

| Failure | A | B | C |
|---|---|---|---|
| vlr.gg / Cloudflare challenges datacenter IPs | possible: test with one request from the box before relying on it; Kalshi unaffected | same | likelier (shared Azure ranges, many scrapers) |
| Process dies silently | `healthchecks.io` free ping at the end of each run → email after 2 missed runs | same | same; GitHub also auto-disables scheduled workflows on public repos after 60 days without commits |
| Disk / VM loss | nightly `sqlite3 .backup` → compressed → R2/B2 (≤ 24 h loss) | managed DB; daily backups on Pro only | managed DB |
| Clock / timezone | UTC cron, NTP default | same | UTC |
| Credentials | Kalshi market data is public; no secrets needed for the logger. Trading keys (later) stay in a 0600 `.env` on the box, never in git | Supabase service key on the box | Supabase key as a repo secret |
| Maintenance | `unattended-upgrades`; one box to patch | + Supabase dashboard | none |
| Cost creep | fixed | free tier → $25 cliff | minutes overage if private |

## Recommendation

**A.** It's the cheapest option that still captures the T − 60 min price and the close on time. It
needs no code changes (copy the repo, create a venv, add a crontab line). It can later host the
shadow quoter and the pricing bot, which the pricing repo's CLAUDE.md already plans to run on a
cloud VM. Add Supabase (B) only if something other than that box needs to query the odds live.

Rollout once you approve:
1. Create the VPS (ARM is fine; all dependencies have wheels), plus a non-root user and SSH key.
2. `git clone` (public branch) → `uv venv` → `uv pip install -r` → run one poll by hand;
   check that the vlr and Kalshi rows land.
3. Add crontab `*/15 * * * *` for the logger (and `5-59/15` for the shadow quoter if wanted).
   Add a nightly backup to R2/B2 and a healthchecks.io ping.
4. Run both machines in parallel for 48 h and diff row counts.
5. Then disable the laptop task (`Unregister-ScheduledTask ThunderedgeOddsLogger`).

## Decisions needed

1. Approve A (or B/C) and the provider.
2. Approve the tighter in-season vlr cadence above (≈ 300 requests/day during Kickoff, versus
   ≈ 900 now). Say whether logger requests count against the page cap.

Sources for the price/limit claims (third-party summaries, checked 2026-11-17):
- [Hetzner price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- [Hetzner 2026 pricing summary](https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/)
- [Supabase free-tier limits 2026](https://automationatlas.io/answers/supabase-free-tier-limits-2026/)
- [Supabase pricing guide](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/)
- [GitHub Actions cron delays and skipped runs](https://dev.to/ksivamuthu/github-actions-scheduled-workflows-understanding-the-limitations-and-possible-solutions-5hm5)
- [GitHub status: Actions start delays, July 2026](https://www.githubstatus.com/incidents/fw294tth5m8y)
