# DraftKings Fantasy Sports Tools

Two independent tools live in this repo:

- **`bestball/`** — a simulation of a DraftKings Best Ball Mania-style NFL
  contest (draft, real historical scoring, standings/payouts).
- **`mlb_dfs/`** — an exact lineup optimizer for DraftKings Classic MLB
  daily fantasy contests.

## NFL Best Ball Contest Simulation

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

## NFL project layout

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
```

---

## DraftKings Classic MLB DFS Lineup Optimizer

Given a player pool (salary, position eligibility, team/opponent, and a
projection), `mlb_dfs` finds the **provably highest-projection valid
lineup** for DraftKings' Classic MLB contest format, using an exact integer
program (via [PuLP](https://coin-or.github.io/pulp/)/CBC) rather than a
greedy heuristic:

- 10 roster slots: `P P C 1B 2B 3B SS OF OF OF`, multi-position players
  (e.g. `1B/OF`) handled correctly.
- $50,000 salary cap.
- DK's own construction rules: no more than 5 hitters from one real MLB
  team, and players drawn from at least 2 different games on the slate.
- Optional player locks/exclusions, and generating N diverse lineups at
  once (bounded overlap between them) for multi-entry GPPs.

### Live data — why you have to supply the slate

This environment's network egress policy blocks `draftkings.com` outright,
and every third-party sports/DFS data site tried while building this
(`rotogrinders.com`, `rotowire.com`, `fantasypros.com`, `mlb.com`,
`espn.com`, `statsapi.mlb.com`, even `en.wikipedia.org`) — the same
organization-level allowlist decision documented in the NFL section above
for `occupyfantasy.com`. Unlike the Best Ball ADP case, there's no
single static snapshot to check in here: the MLB slate, salaries, and
starting lineups are different **every single day**, so there is nothing
that could be captured once and reused.

This isn't actually a gap specific to this environment, though: DraftKings
has no public API for its live salary pool, so real MLB DFS optimizer
tools all work the same way — you export today's slate yourself from the
DK site (**Lineup Builder → Export to CSV** on the contest you want to
optimize) and hand that file to the tool. `mlb_dfs/slate.py` parses that
exact export format.

### Quick start

```bash
pip install -r requirements.txt
python -m mlb_dfs.cli --salaries DKSalaries.csv
```

Optional: override DK's own `AvgPointsPerGame` projection with your own,
via a `name,projection` CSV:

```bash
python -m mlb_dfs.cli --salaries DKSalaries.csv --projections my_projections.csv
```

Generate 3 diverse lineups for multi-entry, or lock/exclude specific
players (DK player IDs, from the salary CSV's `ID` column):

```bash
python -m mlb_dfs.cli --salaries DKSalaries.csv --lineups 3 --max-overlap 7
python -m mlb_dfs.cli --salaries DKSalaries.csv --lock 12345678 --exclude 87654321
```

There's also a bundled **synthetic** demo slate (fictional players/teams,
not a real date) for trying the tool without a real export:

```bash
python -m mlb_dfs.cli --sample
```

### Library usage

```python
from mlb_dfs import load_dk_export, optimize

players = load_dk_export("DKSalaries.csv")
lineup = optimize(players)
for label, p in lineup.slots:
    print(label, p.name, p.team, p.salary, p.projection)
print(lineup.total_salary, lineup.total_projection)
```

### MLB project layout

```
mlb_dfs/
  player.py     Player dataclass + multi-position eligibility parsing
  slate.py      loads DK's Classic MLB CSV export format; sample-slate loader
  optimizer.py  exact ILP lineup solver (salary cap, team-hitter cap, min-games rule)
  cli.py        command-line entry point
data/
  sample_dk_mlb_slate.csv   synthetic demo slate for --sample / tests (not real data)
```

## Tests

```bash
python -m unittest discover -s tests -v
```
