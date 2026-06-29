"""Generate cached entries data and charts from original results CSV files.

The script loads the results CSV files for the 2023-2024, 2024-2025, and
2025-2026 seasons from ``data/original_website/files/results/2020-2030``.
It writes a combined parquet cache for downstream analysis and creates a PNG
bar chart showing entries per round for the 2025-2026 season.
It also writes a grouped bar chart with all three seasons shown side by side
for each round.
It also writes individual season bar charts for each junior and adult age
group, split by gender.
It also writes a season summary bar chart showing distinct athletes per season.
It also writes a season summary bar chart split into junior and adult cohorts.
"""

from __future__ import annotations

import argparse
from io import StringIO
import re
from pathlib import Path
from typing import Iterable

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_ROOT = (
    ROOT_DIR / "data" / "original_website" / "files" / "results" / "2020-2030"
)
OUTPUT_DIR = ROOT_DIR / "data" / "generated" / "entries_report"
PARQUET_PATH = OUTPUT_DIR / "entries_all_seasons.parquet"
CHART_PATH = OUTPUT_DIR / "entries_per_round_2025_2026.png"
GROUPED_CHART_PATH = OUTPUT_DIR / "entries_per_round_by_season.png"
TARGET_SEASONS = {"2023-2024", "2024-2025", "2025-2026"}
ENCODINGS = ["utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "latin1"]
AGE_GROUPS = ["U9", "U11", "U13", "U15", "U17"]
ADULT_GROUPS = ["U20", "Senior", "V40", "V50", "V60", "V70"]
JUNIOR_GENDERS = ["Boys", "Girls"]
ADULT_GENDERS = ["Men", "Women"]
SEASON_ORDER = ["2023-2024", "2024-2025", "2025-2026"]
SEASON_PALETTE = sns.color_palette("deep", len(SEASON_ORDER))
SEASON_COLOR_MAP = dict(zip(SEASON_ORDER, SEASON_PALETTE))
JUNIOR_PANEL_PATH = OUTPUT_DIR / "junior_participation_panel.png"
ADULT_PANEL_PATH = OUTPUT_DIR / "adult_participation_panel.png"
SEASON_SUMMARY_PATH = OUTPUT_DIR / "distinct_athletes_by_season.png"
SEASON_SUMMARY_SPLIT_PATH = OUTPUT_DIR / "distinct_athletes_by_season_split.png"


def decode_text(data: bytes) -> str:
    """Decode a CSV file using the encodings used by the original website."""

    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode results CSV using known encodings")


def collect_csv_files(base_dir: Path, seasons: set[str]) -> list[Path]:
    """Return all CSV files for the requested seasons."""

    csv_files: list[Path] = []
    for season in sorted(seasons):
        season_dir = base_dir / season
        if not season_dir.exists():
            continue
        csv_files.extend(sorted(season_dir.glob("r*.csv")))
        csv_files.extend(sorted(season_dir.glob("r*/*.csv")))
    return sorted({path for path in csv_files if path.is_file()})


def parse_round_name(path: Path) -> str:
    """Extract the round name from a CSV path."""

    return path.parent.name


def parse_season_name(path: Path) -> str:
    """Extract the season name from a CSV path."""

    return path.parents[1].name


def parse_category_name(path: Path) -> str:
    """Extract the category slug from a CSV filename."""

    return path.stem.rsplit("-", 1)[-1]


def parse_file_gender(path: Path) -> str | None:
    """Extract a gender label from the source filename when one is present."""

    stem = path.stem.lower()
    if "boys" in stem:
        return "Boys"
    if "girls" in stem:
        return "Girls"
    if "women" in stem:
        return "Women"
    if "men" in stem:
        return "Men"
    return None


def infer_age_group(category_name: str) -> str | None:
    """Map a category slug to a participation age group when applicable."""

    lowered = category_name.lower()
    for band in AGE_GROUPS:
        if band.lower() in lowered:
            return band
    return None


def extract_sex_group(category_name: str, row: pd.Series) -> str | None:
    """Extract a Boys/Girls label from the filename or parsed row values."""

    match = re.search(r"(Boys|Girls)", category_name, flags=re.IGNORECASE)
    if match:
        return match.group(1).title()

    for value in row.astype(str):
        match = re.search(r"\b(Boys|Girls)\b", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).title()

        value_upper = value.strip().upper()
        if value_upper in {"MALE", "M", "U9B", "U11B", "U13B", "U15B", "U17M", "U17B"}:
            return "Boys"
        if value_upper in {
            "FEMALE",
            "F",
            "U9G",
            "U11G",
            "U13G",
            "U15G",
            "U17W",
            "U17G",
        }:
            return "Girls"
    return None


def extract_junior_gender(file_gender: str | None, row: pd.Series) -> str | None:
    """Extract a junior gender label from the source row."""

    if file_gender in {"Boys", "Girls"}:
        return file_gender

    for value in row.astype(str):
        match = re.search(r"\b(Boys|Girls)\b", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).title()

        value_upper = value.strip().upper()
        if value_upper in {"MALE", "M", "U9B", "U11B", "U13B", "U15B", "U17M", "U17B"}:
            return "Boys"
        if value_upper in {
            "FEMALE",
            "F",
            "U9G",
            "U11G",
            "U13G",
            "U15G",
            "U17W",
            "U17G",
        }:
            return "Girls"

    return None


def extract_adult_gender(file_gender: str | None, row: pd.Series) -> str | None:
    """Extract an adult gender label from the source row."""

    if file_gender in {"Men", "Women"}:
        return file_gender

    for value in row.astype(str):
        match = re.search(r"\b(Men|Women)\b", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).title()

        value_upper = value.strip().upper()
        if value_upper in {"MALE", "M", "SM", "MV40", "MV50", "MV60", "MV70", "U20M"}:
            return "Men"
        if value_upper in {"FEMALE", "F", "SW", "WV40", "WV50", "WV60", "WV70", "U20W"}:
            return "Women"

    return None


def extract_adult_group(row: pd.Series) -> str | None:
    """Extract an adult age-group label from any cell in a parsed CSV row."""

    normalized_values = [re.sub(r"\s+", "", value).upper() for value in row.astype(str)]

    veteran_patterns = [
        ("V70", re.compile(r"^(?:[MW])?V70\+?$")),
        ("V60", re.compile(r"^(?:[MW])?V60\+?$")),
        ("V50", re.compile(r"^(?:[MW])?V50\+?$")),
        ("V40", re.compile(r"^(?:[MW])?V40\+?$")),
    ]
    for adult_group, pattern in veteran_patterns:
        if any(pattern.match(value) for value in normalized_values):
            return adult_group

    if any(value.startswith("U20") for value in normalized_values):
        return "U20"

    if any(
        value.startswith("SENIOR") or value in {"SM", "SW"}
        for value in normalized_values
    ):
        return "Senior"

    return None


def load_results_csv(path: Path) -> pd.DataFrame:
    """Load one UTF-16 results CSV into a normalised DataFrame."""

    text = decode_text(path.read_bytes())
    frame = pd.read_csv(StringIO(text))
    file_gender = parse_file_gender(path)
    frame["season"] = parse_season_name(path)
    frame["round"] = parse_round_name(path)
    frame["category_name"] = parse_category_name(path)
    frame["age_group"] = infer_age_group(frame["category_name"].iat[0])
    frame["junior_gender"] = frame.apply(
        lambda row: extract_junior_gender(file_gender, row), axis=1
    )
    frame["adult_gender"] = frame.apply(
        lambda row: extract_adult_gender(file_gender, row), axis=1
    )
    frame["sex_group"] = frame["junior_gender"].combine_first(frame["adult_gender"])
    frame["gender_group"] = frame["sex_group"]
    frame["adult_group"] = frame.apply(extract_adult_group, axis=1)
    frame["source_file"] = path.name
    return frame


def build_results_table(csv_files: Iterable[Path]) -> pd.DataFrame:
    """Load and combine all requested results CSV files."""

    frames = [load_results_csv(path) for path in csv_files]
    if not frames:
        raise FileNotFoundError(
            f"No results CSV files found under {RESULTS_ROOT} for {sorted(TARGET_SEASONS)}"
        )
    return pd.concat(frames, ignore_index=True)


def write_parquet_cache(frame: pd.DataFrame, parquet_path: Path) -> None:
    """Persist the combined results table as parquet using DuckDB."""

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("entries_frame", frame)
        connection.execute(
            f"COPY entries_frame TO '{parquet_path.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        connection.close()


def query_parquet(parquet_path: Path, query: str) -> pd.DataFrame:
    """Execute a DuckDB query against the generated parquet cache."""

    connection = duckdb.connect(database=":memory:")
    try:
        return connection.execute(
            query.replace("{parquet_path}", parquet_path.as_posix())
        ).fetchdf()
    finally:
        connection.close()


def build_round_chart(parquet_path: Path, chart_path: Path) -> None:
    """Create a bar chart of entries per round for the 2025-2026 season."""

    chart_data = query_parquet(
        parquet_path,
        """
        SELECT
            round,
            CAST(regexp_extract(round, '(\\d+)', 1) AS INTEGER) AS round_number,
            COUNT(*) AS entries
        FROM read_parquet('{parquet_path}')
        WHERE season = '2025-2026'
        GROUP BY round, round_number
        ORDER BY round_number
        """,
    )

    if chart_data.empty:
        raise ValueError("No rows found for season 2025-2026")

    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(8, 5))
    ax = sns.barplot(data=chart_data, x="round", y="entries", color="#1f77b4")
    ax.set_title("Participants per round - 2025-2026")
    ax.set_xlabel("Round")
    ax.set_ylabel("Participants")
    ax.bar_label(ax.containers[0], fmt="%d", padding=3)
    plt.tight_layout()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(chart_path, dpi=200, bbox_inches="tight")
    plt.close()


def build_grouped_round_chart(parquet_path: Path, chart_path: Path) -> None:
    """Create a grouped bar chart of entries per round across all seasons."""

    chart_data = query_parquet(
        parquet_path,
        """
        SELECT
            round,
            CAST(regexp_extract(round, '(\\d+)', 1) AS INTEGER) AS round_number,
            season,
            COUNT(*) AS entries
        FROM read_parquet('{parquet_path}')
        GROUP BY round, round_number, season
        ORDER BY round_number, season
        """,
    )

    round_order = chart_data.sort_values("round_number")["round"].drop_duplicates()

    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(10, 5))
    ax = sns.barplot(
        data=chart_data,
        x="round",
        y="entries",
        hue="season",
        order=round_order,
        hue_order=sorted(TARGET_SEASONS),
        palette="deep",
    )
    ax.set_title("Participation per round by season")
    ax.set_xlabel("Round")
    ax.set_ylabel("Participants")
    ax.legend(title="Season")
    plt.tight_layout()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(chart_path, dpi=200, bbox_inches="tight")
    plt.close()


def build_season_summary_chart(parquet_path: Path, chart_path: Path) -> None:
    """Create a bar chart of distinct athletes per season."""

    chart_data = query_parquet(
        parquet_path,
        """
        SELECT
            season,
            COUNT(DISTINCT athlete_name) AS distinct_athletes
        FROM read_parquet('{parquet_path}')
        GROUP BY season
        ORDER BY season
        """,
    )

    chart_data = (
        chart_data.set_index("season").reindex(SEASON_ORDER, fill_value=0).reset_index()
    )

    figure, axis = plt.subplots(figsize=(7, 4))
    bars = axis.bar(
        chart_data["season"],
        chart_data["distinct_athletes"],
        color=[SEASON_COLOR_MAP[season] for season in chart_data["season"]],
    )
    axis.set_title("Distinct athletes per season")
    axis.set_xlabel("Season")
    axis.set_ylabel("total participations (sum)")
    axis.set_ylim(0, max(1, int(chart_data["distinct_athletes"].max() * 1.15) + 1))
    axis.tick_params(axis="x", rotation=20)
    axis.bar_label(bars, fmt="%d", padding=2, fontsize=8)
    figure.tight_layout()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(chart_path, dpi=200, bbox_inches="tight")
    plt.close(figure)


def build_season_summary_split_chart(parquet_path: Path, chart_path: Path) -> None:
    """Create a bar chart of distinct athletes per season split by cohort."""

    chart_data = query_parquet(
        parquet_path,
        """
        SELECT
            season,
            CASE
                WHEN age_group IS NOT NULL THEN 'Junior'
                ELSE 'Adult'
            END AS cohort,
            COUNT(DISTINCT athlete_name) AS distinct_athletes
        FROM read_parquet('{parquet_path}')
        GROUP BY season, cohort
        ORDER BY season, cohort
        """,
    )

    chart_data = (
        chart_data.pivot(index="season", columns="cohort", values="distinct_athletes")
        .reindex(SEASON_ORDER, fill_value=0)
        .fillna(0)
        .reset_index()
    )

    plot_data = chart_data.melt(
        id_vars="season",
        value_vars=["Junior", "Adult"],
        var_name="cohort",
        value_name="distinct_athletes",
    )

    figure, axis = plt.subplots(figsize=(7, 4))
    ax = sns.barplot(
        data=plot_data,
        x="season",
        y="distinct_athletes",
        hue="cohort",
        order=SEASON_ORDER,
        hue_order=["Junior", "Adult"],
        palette="deep",
        ax=axis,
    )
    ax.set_title("Distinct athletes per season split by cohort")
    ax.set_xlabel("Season")
    ax.set_ylabel("Distinct athletes")
    ax.legend(title="Cohort")
    ax.tick_params(axis="x", rotation=20)
    for container in ax.containers:
        ax.bar_label(container, fmt="%d", padding=2, fontsize=8)
    figure.tight_layout()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(chart_path, dpi=200, bbox_inches="tight")
    plt.close(figure)


def build_group_panel_chart(
    parquet_path: Path,
    chart_path: Path,
    *,
    group_column: str,
    group_order: list[str],
    gender_column: str,
    gender_order: list[str],
    title: str,
) -> None:
    """Create a grid panel of season-based bar charts split by gender."""

    chart_data = query_parquet(
        parquet_path,
        f"""
        SELECT
            season,
            {group_column} AS group_label,
            {gender_column} AS gender_label,
            COUNT(*) AS entries
        FROM read_parquet('{{parquet_path}}')
        WHERE {group_column} IS NOT NULL
          AND {gender_column} IS NOT NULL
        GROUP BY season, group_label, gender_label
        ORDER BY group_label, gender_label, season
        """,
    )

    if chart_data.empty:
        raise ValueError(f"No rows found for {title}")

    figure, axes = plt.subplots(
        len(group_order),
        len(gender_order),
        figsize=(12, max(6, len(group_order) * 2.2)),
        sharex=True,
    )

    for row_index, group_label in enumerate(group_order):
        for col_index, gender_label in enumerate(gender_order):
            axis = axes[row_index, col_index]
            panel_data = (
                chart_data[
                    (chart_data["group_label"] == group_label)
                    & (chart_data["gender_label"] == gender_label)
                ]
                .set_index("season")
                .reindex(SEASON_ORDER, fill_value=0)
            )
            values = [int(value) for value in panel_data["entries"].tolist()]
            bars = axis.bar(
                SEASON_ORDER,
                values,
                color=SEASON_PALETTE,
            )
            axis.set_title(f"{group_label} {gender_label}")
            axis.set_ylim(0, max(1, int(max(values) * 1.15) + 1))
            axis.tick_params(axis="x", rotation=20)
            axis.bar_label(bars, padding=2, fontsize=8)
            if col_index == 0:
                axis.set_ylabel("total participations (sum)")
            if row_index == len(group_order) - 1:
                axis.set_xlabel("Season")

    figure.suptitle(title, y=1.01)
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=SEASON_COLOR_MAP[season])
        for season in SEASON_ORDER
    ]
    figure.legend(legend_handles, SEASON_ORDER, title="Season", loc="upper right")
    figure.tight_layout()
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(chart_path, dpi=200, bbox_inches="tight")
    plt.close(figure)


def build_junior_panel(parquet_path: Path, chart_path: Path) -> None:
    """Create the combined junior participation panel."""

    build_group_panel_chart(
        parquet_path,
        chart_path,
        group_column="age_group",
        group_order=AGE_GROUPS,
        gender_column="junior_gender",
        gender_order=JUNIOR_GENDERS,
        title="Junior participation by age group and gender",
    )


def build_adult_panel(parquet_path: Path, chart_path: Path) -> None:
    """Create the combined adult participation panel."""

    build_group_panel_chart(
        parquet_path,
        chart_path,
        group_column="adult_group",
        group_order=ADULT_GROUPS,
        gender_column="adult_gender",
        gender_order=ADULT_GENDERS,
        title="Adult participation by age group and gender",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for parquet and chart outputs.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate the entries cache and round chart."""

    args = parse_args()
    csv_files = collect_csv_files(RESULTS_ROOT, TARGET_SEASONS)
    results_frame = build_results_table(csv_files)

    parquet_path = args.output_dir / PARQUET_PATH.name
    chart_path = args.output_dir / CHART_PATH.name
    grouped_chart_path = args.output_dir / GROUPED_CHART_PATH.name
    junior_panel_path = args.output_dir / JUNIOR_PANEL_PATH.name
    adult_panel_path = args.output_dir / ADULT_PANEL_PATH.name
    season_summary_path = args.output_dir / SEASON_SUMMARY_PATH.name
    season_summary_split_path = args.output_dir / SEASON_SUMMARY_SPLIT_PATH.name

    write_parquet_cache(results_frame, parquet_path)
    build_round_chart(parquet_path, chart_path)
    build_grouped_round_chart(parquet_path, grouped_chart_path)
    build_junior_panel(parquet_path, junior_panel_path)
    build_adult_panel(parquet_path, adult_panel_path)
    build_season_summary_chart(parquet_path, season_summary_path)
    build_season_summary_split_chart(parquet_path, season_summary_split_path)

    print(f"Loaded {len(csv_files)} CSV files")
    print(f"Wrote parquet cache: {parquet_path}")
    print(f"Wrote round chart: {chart_path}")
    print(f"Wrote grouped round chart: {grouped_chart_path}")
    print(f"Wrote junior panel: {junior_panel_path}")
    print(f"Wrote adult panel: {adult_panel_path}")
    print(f"Wrote season summary chart: {season_summary_path}")
    print(f"Wrote split season summary chart: {season_summary_split_path}")


if __name__ == "__main__":
    main()
