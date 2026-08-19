"""Real DraftKings Best Ball ADP, loaded from a locally-stored snapshot.

occupyfantasy.com's DK Best Ball ADP page (the source of this snapshot) is
blocked by this environment's network egress policy, so it can't be
re-fetched live at run time. Instead we ship the snapshot the user supplied
as ``data/dk_best_ball_adp_2026.csv`` and load it here. This is real DK
Best Ball ADP for the upcoming 2026 season draft class (it includes 2026
rookies) -- not the points-above-replacement proxy in ``players.py``.

Note: nflverse's live player_stats feed only has real game results through
the 2024 season as of this writing (no 2025 season box scores yet, and 2026
hasn't been played). So a league built with this ADP and scored against
``season=2024`` real results is a "2026 market, 2024 results" backtest, not
a live replay of the season this ADP is actually for -- see the season
simulation docs for how ``season`` and the ADP vintage are kept separate.

Matching to nflverse player rows is done by normalized name + position
(not team: a player's ADP-snapshot team can differ from whatever season's
box scores we're scoring against, e.g. after a trade or free agency move).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "dk_best_ball_adp_2026.csv"

_SUFFIXES = (" jr", " sr", " ii", " iii", " iv", " v")

# A handful of confirmed nickname/formal-name mismatches between the ADP
# snapshot and nflverse's player_display_name, verified individually (not
# fuzzy-matched -- last-name-only matching produced too many false positives
# between unrelated players who happen to share a surname).
_NAME_ALIASES = {
    "kenny gainwell": "kenneth gainwell",
    "chig okonkwo": "chigoziem okonkwo",
    "joshua palmer": "josh palmer",
}


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = name.replace(".", "").replace("'", "").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.strip()
    return _NAME_ALIASES.get(name, name)


def load_live_adp(path: Path | None = None) -> dict[tuple[str, str], float]:
    """Return {(normalized_name, position): adp_value} from the snapshot CSV.

    Lower adp_value means drafted earlier, matching the source data's own
    convention (ADP 1.1 = the 1st overall pick).
    """
    csv_path = path or DEFAULT_PATH
    if not csv_path.exists():
        return {}

    table: dict[tuple[str, str], float] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (normalize_name(row["name"]), row["position"])
            adp = float(row["adp"])
            # Keep the earliest (lowest/best) ADP if a name collides.
            if key not in table or adp < table[key]:
                table[key] = adp
    return table
