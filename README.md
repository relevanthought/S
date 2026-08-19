# DraftKings-style NFL Best Ball Contest Simulation

Simulates a DraftKings Best Ball Mania-style NFL fantasy contest end to end:

1. **Draft** — a snake draft where AI teams pick "best player available" off
   of an ADP-style ranking, with per-pick randomness and positional-need
   logic so rosters come out balanced instead of everyone drafting the same
   guy.
2. **Score** — every roster is scored week by week using **real historical
   NFL results** (via [nflverse](https://github.com/nflverse/nflverse-data)),
   converted to DraftKings' classic scoring rules.
3. **Best Ball lineups** — each week, the optimal starting lineup (the
   highest-scoring eligible players at each slot) is selected automatically,
   exactly like DK's Best Ball product — there's no in-season lineup
   management.
4. **Standings & payouts** — teams are ranked, a subset advance to a
   simplified "playoff" cut, and an illustrative prize payout is computed.

## Quick start

```bash
pip install -r requirements.txt
python -m bestball.cli --teams 12 --seed 42 --show-rosters
```

First run downloads and caches nflverse's `player_stats.csv` (~30MB) into
`data/`; subsequent runs reuse the cache for up to 12 hours (`--refresh-data`
forces a re-download).

### CLI options

| Flag | Default | Meaning |
|---|---|---|
| `--season` | most recent complete season in the data | NFL season to simulate |
| `--teams` | 12 | teams in the league |
| `--seed` | random | seed for reproducible drafts |
| `--advance` | 4 | teams that advance past the regular-season cut |
| `--entry-fee` | 25 | contest buy-in, for the illustrative payout curve |
| `--rake` | 0.15 | platform rake taken out of the prize pool |
| `--show-rosters` | off | print the full draft board |
| `--refresh-data` | off | force re-download of the stats cache |

## Library usage

```python
from bestball import season

result = season.simulate_league(season=2024, num_teams=12, seed=42)
for r in result.results:
    print(r.final_rank, r.team.name, r.regular_season_total, r.playoff_total, r.payout)
```

## Design notes / assumptions

This project pulls real data wherever a live, publicly reachable source
exists, and is explicit about the pieces that don't have one:

- **Real weekly scores**: `bestball/data.py` downloads nflverse's
  `player_stats.csv` release directly from GitHub — actual NFL box-score
  stats (passing/rushing/receiving) for every player, every week, back to
  1999. Scoring is computed with DraftKings' published classic rules
  (`bestball/scoring.py`): full PPR, 0.04/0.1 pt per pass/rush-rec yard, 4/6
  pt TDs, -1 INT/fumble lost, and the 100/300-yard bonuses.
- **Real DK Best Ball ADP**: `data/dk_best_ball_adp_2026.csv` is a real DK
  Best Ball ADP snapshot for the **upcoming 2026 season draft class** (442
  players, including 2026 rookies), sourced from
  [occupyfantasy.com/draftkings-best-ball-adp](https://occupyfantasy.com/draftkings-best-ball-adp/).
  That site itself is blocked by this environment's network egress policy
  (confirmed via both a direct fetch and the fetch tool — an org-level
  allowlist decision, not something code can route around), so the snapshot
  was captured externally and checked in rather than scraped live at
  runtime. `bestball/live_adp.py` loads it and matches players by
  normalized name + position (not team, since a player's snapshot-time team
  can differ from whatever season's box scores we're scoring against). For
  any player not in the snapshot — a real gap, since it's a single point-in-
  time capture, not a live-refreshing feed — `bestball/players.py` falls
  back to a proxy: prior-season real DK points converted to points-above-
  replacement (a standard sabermetric-style technique) so positional
  scarcity behaves realistically. Both paths only use information that would
  genuinely have been known before the simulated season started.
- **ADP vintage vs. scored season are independent, and that's a real gap**:
  nflverse's live results feed only has real box scores through the **2024**
  season as of this writing — no 2025 season data yet (nflverse hasn't
  published it), and 2026 hasn't been played. So running this project's
  default `--season` (2024, the most recent complete season actually
  fetchable) against the 2026 ADP snapshot is a **"2026 market, 2024
  results" backtest** — real draft signal, replayed against the most recent
  real season available, not a literal simulation of the 2026 season itself.
  2026 rookies in the ADP snapshot correctly have no matching box scores
  yet and fall back to the proxy (which is nearly a no-op for them, since
  they also have no prior-season data — they just draft late). If real 2025
  weekly results become fetchable, or you have them from another source,
  pointing `data.load_weekly_rows` at 2025 would close this gap.
- **Roster construction rules**: DK's exact Best Ball roster-construction
  limits aren't published in a way this environment can fetch, so
  `bestball/draft.py` uses a documented, reasonable approximation (20
  rounds, 1 QB/2 RB/3 WR/1 TE/1 FLEX starters, no K/DST, position
  min/max/soft-target constants you can tune).
- **Payouts**: DK's real per-contest payout tables are contest-specific and
  not fetchable live, so `bestball/payouts.py` builds a generic top-heavy
  GPP-style payout curve from the entry fee/rake/field size — illustrative,
  not DK's actual numbers.
- **Playoff cut**: a simplified two-stage structure (weeks 1-14 regular
  season, top N teams carry into a weeks 15-17 "playoff") that mirrors the
  *shape* of DK's multi-week Best Ball tournaments without claiming to
  reproduce their exact (much larger, multi-round) bracket mechanics.

## Project layout

```
bestball/
  data.py      nflverse fetch/cache + raw stat loading
  scoring.py   DraftKings classic fantasy scoring formula
  live_adp.py  loads the real DK Best Ball ADP snapshot, name/position matching
  players.py   season player pool: live ADP + points-above-replacement fallback
  draft.py     snake draft simulation with AI opponents
  lineup.py    exact optimal weekly Best Ball lineup solver
  season.py    orchestrates draft + weekly scoring + standings/payouts + seed sweeps
  payouts.py   illustrative GPP payout curve
  cli.py       command-line entry point
data/
  dk_best_ball_adp_2026.csv   real DK Best Ball ADP snapshot for 2026 (checked in; source site is network-blocked)
tests/         unit tests (scoring math, lineup optimizer vs. brute force, draft roster rules, ADP matching)
```

## Tests

```bash
python -m unittest discover -s tests -v
```
