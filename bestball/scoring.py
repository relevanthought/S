"""DraftKings classic NFL fantasy scoring (used by DK Best Ball contests).

Rules (per DraftKings' published NFL scoring rules):

Passing
    Passing Yard:        0.04 pts (1 pt per 25 yards)
    Passing TD:           4 pts
    Interception:        -1 pt
    300+ Passing Yard Game: +3 pts bonus
    2-pt conversion:      2 pts

Rushing
    Rushing Yard:         0.1 pts (1 pt per 10 yards)
    Rushing TD:            6 pts
    100+ Rushing Yard Game: +3 pts bonus
    2-pt conversion:      2 pts

Receiving (full PPR)
    Reception:             1 pt
    Receiving Yard:       0.1 pts (1 pt per 10 yards)
    Receiving TD:           6 pts
    100+ Receiving Yard Game: +3 pts bonus
    2-pt conversion:      2 pts

Misc
    Fumble Lost:          -1 pt
    Punt/Kickoff/FG return TD: 6 pts
"""

from __future__ import annotations

PASSING_YARD_BONUS_THRESHOLD = 300
RUSHING_YARD_BONUS_THRESHOLD = 100
RECEIVING_YARD_BONUS_THRESHOLD = 100
YARDAGE_BONUS = 3.0


def dk_points(stat_row: dict) -> float:
    """Compute DraftKings classic fantasy points for one player-week row.

    ``stat_row`` is expected to have the nflverse player_stats column names
    (passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds,
    receptions, receiving_yards, receiving_tds, *_fumbles_lost,
    *_2pt_conversions, special_teams_tds), all numeric.
    """
    g = lambda k: float(stat_row.get(k, 0) or 0)

    points = 0.0

    # Passing
    points += g("passing_yards") * 0.04
    points += g("passing_tds") * 4.0
    points += g("interceptions") * -1.0
    points += g("passing_2pt_conversions") * 2.0
    if g("passing_yards") >= PASSING_YARD_BONUS_THRESHOLD:
        points += YARDAGE_BONUS

    # Rushing
    points += g("rushing_yards") * 0.1
    points += g("rushing_tds") * 6.0
    points += g("rushing_2pt_conversions") * 2.0
    if g("rushing_yards") >= RUSHING_YARD_BONUS_THRESHOLD:
        points += YARDAGE_BONUS

    # Receiving (full PPR)
    points += g("receptions") * 1.0
    points += g("receiving_yards") * 0.1
    points += g("receiving_tds") * 6.0
    points += g("receiving_2pt_conversions") * 2.0
    if g("receiving_yards") >= RECEIVING_YARD_BONUS_THRESHOLD:
        points += YARDAGE_BONUS

    # Fumbles lost (any of the three tracked categories)
    fumbles_lost = (
        g("sack_fumbles_lost") + g("rushing_fumbles_lost") + g("receiving_fumbles_lost")
    )
    points += fumbles_lost * -1.0

    # Return TDs
    points += g("special_teams_tds") * 6.0

    return round(points, 2)
