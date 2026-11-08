"""Shared OXL category definitions for scoring and standings navigation."""

import re
from collections.abc import Iterable

from pyresults import (
    Category,
    CategoryType,
    CompetitionConfig,
    Gender,
    build_default_config,
)

from website.models import StandingCategory

_JUNIOR_TEAM_SIZE = 3
_EVEN_JUNIOR_FORMAT_START_YEAR = 2026
_HISTORICAL_JUNIOR_CATEGORY_CODES = (
    "U9B",
    "U9G",
    "U11B",
    "U11G",
    "U13B",
    "U13G",
    "U15B",
    "U15G",
    "U17M",
    "U17W",
)
_JUNIOR_TEAM_CATEGORIES = (
    (
        "U10B",
        "Under 10 Boys",
        Gender.MALE,
        "U10",
        ("U10B", "U10 Boys", "Under 10 Boys"),
    ),
    (
        "U10G",
        "Under 10 Girls",
        Gender.FEMALE,
        "U10",
        ("U10G", "U10 Girls", "Under 10 Girls"),
    ),
    (
        "U12B",
        "Under 12 Boys",
        Gender.MALE,
        "U12",
        ("U12B", "U12 Boys", "Under 12 Boys"),
    ),
    (
        "U12G",
        "Under 12 Girls",
        Gender.FEMALE,
        "U12",
        ("U12G", "U12 Girls", "Under 12 Girls"),
    ),
    (
        "U14B",
        "Under 14 Boys",
        Gender.MALE,
        "U14",
        ("U14B", "U14 Boys", "Under 14 Boys"),
    ),
    (
        "U14G",
        "Under 14 Girls",
        Gender.FEMALE,
        "U14",
        ("U14G", "U14 Girls", "Under 14 Girls"),
    ),
    (
        "U16B",
        "Under 16 Boys",
        Gender.MALE,
        "U16",
        ("U16B", "U16 Boys", "Under 16 Boys"),
    ),
    (
        "U16G",
        "Under 16 Girls",
        Gender.FEMALE,
        "U16",
        ("U16G", "U16 Girls", "Under 16 Girls"),
    ),
    (
        "U18M",
        "Under 18 Men",
        Gender.MALE,
        "U18",
        ("U18M", "U18 Boys", "U18 Men", "Under 18 Boys", "Under 18 Men"),
    ),
    (
        "U18W",
        "Under 18 Women",
        Gender.FEMALE,
        "U18",
        ("U18W", "U18 Girls", "U18 Women", "Under 18 Girls", "Under 18 Women"),
    ),
)
_ADDITIONAL_INDIVIDUAL_CATEGORIES = (
    ("M35", "Men V35", Gender.MALE, "Men", "V35"),
    ("M45", "Men V45", Gender.MALE, "Men", "V45"),
    ("M55", "Men V55", Gender.MALE, "Men", "V55"),
    ("M65", "Men V65", Gender.MALE, "Men", "V65"),
    ("M75", "Men V75", Gender.MALE, "Men", "V75"),
    ("W35", "Women V35", Gender.FEMALE, "Women", "V35"),
    ("W45", "Women V45", Gender.FEMALE, "Women", "V45"),
    ("W55", "Women V55", Gender.FEMALE, "Women", "V55"),
    ("W65", "Women V65", Gender.FEMALE, "Women", "V65"),
)
_CATEGORY_ALIASES: dict[str, str] = {
    alias.casefold(): code
    for code, _, _, _, aliases in _JUNIOR_TEAM_CATEGORIES
    for alias in aliases
}
_CATEGORY_ALIASES.update(
    {
        "u9 boys": "U9B",
        "u9 girls": "U9G",
        "u11 boys": "U11B",
        "u11 girls": "U11G",
        "u13 boys": "U13B",
        "u13 girls": "U13G",
        "u15 boys": "U15B",
        "u15 girls": "U15G",
        "u17 boys": "U17M",
        "u17 girls": "U17W",
    }
)
_CATEGORY_ALIASES.update(
    {
        "u23m": "SM",
        "u23 men": "SM",
        "under 23 men": "SM",
        "u23w": "SW",
        "u23 women": "SW",
        "under 23 women": "SW",
        "m40": "MV40",
        "m50": "MV50",
        "m60": "MV60",
        "m70": "MV70",
        "w40": "WV40",
        "w50": "WV50",
        "w60": "WV60",
        "w70": "WV70",
        "senior men": "SM",
        "senior women": "SW",
    }
)
_RACE_ALIASES = {
    "u20/senior/masters men": "Men",
    "u20/senior/masters women": "Women",
}


def add_oxl_categories(config: CompetitionConfig) -> None:
    """Add the current OXL categories alongside historical pyresults categories."""
    categories = config.category_config.categories
    for code, name, gender, race_name, _ in _JUNIOR_TEAM_CATEGORIES:
        categories.setdefault(
            code,
            Category(
                code=code,
                name=name,
                category_type=CategoryType.TEAM,
                gender=gender,
                race_name=race_name,
                team_size=_JUNIOR_TEAM_SIZE,
                age_group=race_name,
            ),
        )

    for code, name, gender, race_name, age_group in _ADDITIONAL_INDIVIDUAL_CATEGORIES:
        config.category_config.categories.setdefault(
            code,
            Category(
                code=code,
                name=name,
                category_type=CategoryType.INDIVIDUAL,
                gender=gender,
                race_name=race_name,
                age_group=age_group,
            ),
        )


def _uses_even_junior_categories(season_name: str) -> bool:
    """Use even junior bands starting with the 2026-2027 season."""
    match = re.search(r"\b(\d{4})\b", season_name)
    return bool(match and int(match.group(1)) >= _EVEN_JUNIOR_FORMAT_START_YEAR)


def scoring_category(category: str) -> str:
    """Return the canonical category code used for scoring."""
    stripped = category.strip()
    return _CATEGORY_ALIASES.get(stripped.casefold(), stripped)


def team_race_name(race_name: str) -> str:
    """Map production race titles to the configured scoring race names."""
    normalized = re.sub(r"\s*/\s*", "/", " ".join(race_name.casefold().split()))
    if normalized in _RACE_ALIASES:
        return _RACE_ALIASES[normalized]
    age_group = re.match(r"u(\d+)\b", normalized)
    if age_group:
        return f"U{age_group.group(1)}"
    return race_name.strip()


def standing_category_catalog(season_name: str) -> list[StandingCategory]:
    """Return this season's official individual/team tabs, including empty ones."""
    config = build_default_config()
    add_oxl_categories(config)
    incompatible_junior_codes = _incompatible_junior_codes(season_name)
    catalog: dict[tuple[str, str], StandingCategory] = {}

    for category in config.category_config.get_categories_by_type(
        CategoryType.INDIVIDUAL
    ):
        if category.code in incompatible_junior_codes:
            continue
        catalog[(category.code, "individual")] = StandingCategory(
            category=category.code, type="individual", count=0
        )

    for category in config.category_config.get_categories_by_type(CategoryType.TEAM):
        if category.code in incompatible_junior_codes:
            continue
        catalog[(category.code, "team")] = StandingCategory(
            category=category.code, type="team", count=0
        )
        if category.age_group and category.age_group.startswith("U"):
            catalog[(category.code, "individual")] = StandingCategory(
                category=category.code, type="individual", count=0
            )

    return sorted(
        catalog.values(),
        key=lambda item: (
            item.type,
            _category_sort_key(item.category),
        ),
    )


def merge_standing_categories(
    configured: Iterable[StandingCategory],
    stored: Iterable[StandingCategory],
    season_name: str,
) -> list[StandingCategory]:
    """Add stored categories and counts to the configured catalog."""
    incompatible_junior_codes = _incompatible_junior_codes(season_name)
    merged = {
        (category.category, category.type): category
        for category in configured
        if category.category not in {"U23M", "U23W"}
        and category.category not in incompatible_junior_codes
    }
    for category in stored:
        if category.type == "individual" and category.category in {"U23M", "U23W"}:
            senior = "SM" if category.category == "U23M" else "SW"
            senior_key = (senior, category.type)
            senior_category = merged[senior_key]
            merged[senior_key] = senior_category.model_copy(
                update={"count": senior_category.count + category.count}
            )
            continue
        if category.category in incompatible_junior_codes:
            continue
        key = (category.category, category.type)
        current = merged.get(key)
        merged[key] = (
            category
            if current is None
            else current.model_copy(update={"count": current.count + category.count})
        )
    return sorted(
        merged.values(),
        key=lambda item: (
            item.type,
            _category_sort_key(item.category),
        ),
    )


def _incompatible_junior_codes(season_name: str) -> set[str]:
    if _uses_even_junior_categories(season_name):
        return set(_HISTORICAL_JUNIOR_CATEGORY_CODES)
    return {definition[0] for definition in _JUNIOR_TEAM_CATEGORIES}


def _category_sort_key(category: str) -> tuple[int, int, int, str]:
    junior = re.fullmatch(r"U(\d+)([A-Z]*)", category)
    if junior:
        gender_order = {"B": 0, "G": 1, "M": 0, "W": 1}.get(junior.group(2), 0)
        return (0, int(junior.group(1)), gender_order, category)

    if category in {"SM", "SW"}:
        return (1, 0, 0 if category == "SM" else 1, category)

    masters = re.fullmatch(r"(?:MV|WV|M|W)(\d+)", category)
    if masters:
        gender_order = 0 if category.startswith("M") else 1
        return (2, int(masters.group(1)), gender_order, category)

    if category in {"Men", "Women"}:
        return (3, 0, 0 if category == "Men" else 1, category)

    return (4, 0, 0, category.casefold())
