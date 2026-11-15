"""Attach senior division assignments and rankings to team rows."""

from collections import defaultdict
from collections.abc import Sequence
from typing import TypeVar

from website import repository
from website.db import Connection
from website.models import TeamRoundResult, TeamStanding

TeamRow = TypeVar("TeamRow", TeamRoundResult, TeamStanding)

# Temporary mappings for names used in imported results. Keep assignment names
# unchanged; a club identity and alias model should eventually replace these.
_CLUB_ALIASES = {
    "abingdon ac": "abingdon athletics club",
    "banbury harriers ac": "banbury harriers athletic club",
    "headington rr": "headington road runners",
    "highworth rc": "highworth running club",
    "radley athletic club": "radley ac",
    "team kennet tri": "team kennet triathlon & ac",
}


def _score(row: TeamRoundResult | TeamStanding) -> int:
    return row.score if isinstance(row, TeamRoundResult) else row.total_score


def with_divisions(
    db: Connection, season_id: int, rows: Sequence[TeamRow]
) -> list[TeamRow]:
    """Rank senior teams by score within their assigned division and category."""
    assignments = {
        (a.gender, a.club_name.strip().casefold()): a.division
        for a in repository.list_division_assignments(db, season_id)
    }
    groups: dict[tuple[str, int], list[TeamRow]] = defaultdict(list)
    output: list[TeamRow] = []
    for row in rows:
        category = row.category.strip().casefold()
        gender = {
            "men": "men",
            "women": "women",
            "senior men": "men",
            "senior women": "women",
        }.get(category)
        if gender is None:
            output.append(row)
            continue
        club = (row.club or "").strip().casefold()
        division = assignments.get((gender, club))
        if division is None:
            division = assignments.get((gender, _CLUB_ALIASES.get(club, club)), 3)
        groups[(category, division)].append(row)
    for (_, division), group in groups.items():
        group.sort(key=_score)
        previous = None
        position = 0
        for index, row in enumerate(group, 1):
            score = _score(row)
            if score != previous:
                position = index
            previous = score
            output.append(
                row.model_copy(
                    update={"division": division, "division_position": position}
                )
            )
    return output
