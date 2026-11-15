"""Attach senior division assignments and rankings to team rows."""

from collections import defaultdict
from collections.abc import Sequence
from typing import TypeVar, cast

from website import repository
from website.db import Connection
from website.models import TeamRoundResult, TeamStanding
from website.models.competition import Division, DivisionNumber, Gender, Team
from website.services.club_identity import ClubRegistry

TeamRow = TypeVar("TeamRow", TeamRoundResult, TeamStanding)
_GENDERS: dict[str, Gender] = {
    "men": "men",
    "women": "women",
    "senior men": "men",
    "senior women": "women",
}



def _score(row: TeamRoundResult | TeamStanding) -> int:
    return row.score if isinstance(row, TeamRoundResult) else row.total_score


def with_divisions(
    db: Connection, season_id: int, rows: Sequence[TeamRow]
) -> list[TeamRow]:
    """Rank senior teams by score within their assigned division and category."""
    registry = ClubRegistry.load(db)
    assignments = {
        (a.gender, a.club_id): a.division
        for a in repository.list_division_assignments(db, season_id)
    }
    groups: dict[tuple[str, int], list[TeamRow]] = defaultdict(list)
    output: list[TeamRow] = []
    for row in rows:
        category = row.category.strip().casefold()
        gender = _GENDERS.get(category)
        if gender is None:
            output.append(row)
            continue
        club = registry.resolve(row.club)
        number = assignments.get((gender, club.id)) if club else None
        if club is None:
            output.append(
                row.model_copy(
                    update={"team": None, "division": None, "division_position": None}
                )
            )
            continue
        division_ref = (
            Division(
                season_id=season_id, gender=gender, number=cast(DivisionNumber, number)
            )
            if number in (1, 2, 3)
            else None
        )
        team = Team(
            club=club,
            category=row.category,
            label=row.team_label,
            division=division_ref,
        )
        if division_ref is None:
            output.append(
                row.model_copy(
                    update={"team": team, "division": None, "division_position": None}
                )
            )
            continue
        groups[(category, division_ref.number)].append(
            row.model_copy(update={"team": team})
        )
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
