"""Player pool entries for a DraftKings Classic MLB slate."""

from __future__ import annotations

from dataclasses import dataclass, field

# DK's own eligible roster slots, in the order they appear on a Classic MLB
# salary export's "Roster Position" column.
HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF"}
PITCHER_POSITIONS = {"P", "SP", "RP"}


@dataclass(frozen=True)
class Player:
    dk_id: str
    name: str
    positions: tuple[str, ...]
    salary: int
    team: str
    opponent: str
    game_info: str
    projection: float

    @property
    def is_pitcher(self) -> bool:
        return bool(PITCHER_POSITIONS & set(self.positions))

    def eligible_for(self, slot: str) -> bool:
        if slot == "P":
            return self.is_pitcher
        return slot in self.positions

    def value(self) -> float:
        """Projected points per $1,000 salary -- a standard DFS "value" metric."""
        return round(self.projection / (self.salary / 1000.0), 3) if self.salary else 0.0


def normalize_position(raw: str) -> str:
    raw = raw.strip().upper()
    if raw in ("SP", "RP"):
        return "P"
    return raw


def parse_positions(raw: str) -> tuple[str, ...]:
    """DK lists multi-eligible players as e.g. "1B/OF" or "SP/RP"."""
    parts = [normalize_position(p) for p in raw.split("/") if p.strip()]
    # de-dupe while preserving order (SP/RP both collapse to "P")
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return tuple(seen)
