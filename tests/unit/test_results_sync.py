"""Unit tests for ResultsSyncService and category normalisation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

from website import repository
from website.integrations.racetec import RaceTecScrapeError
from website.models import ParsedRaceWithResults, ParsedResult
from website.services.results_sync import (
    MAX_AUTO_SYNC_HOURS,
    ResultsSyncService,
    normalise_category,
)


def test_normalise_category() -> None:
    # Senior & age groups
    assert normalise_category("Senior Men", "Male") == "SM"
    assert normalise_category("Senior Women", "Female") == "SW"
    assert normalise_category("U20 Men", "Male") == "U20M"
    assert normalise_category("U9 Girls", "Female") == "U9G"
    assert normalise_category("U11 Boys", "Male") == "U11B"

    # Veterans mapped by gender
    assert normalise_category("V40", "Male") == "MV40"
    assert normalise_category("V40", "Female") == "WV40"
    assert normalise_category("V50", "M") == "MV50"
    assert normalise_category("V50", "F") == "WV50"
    assert normalise_category("V60", "Male") == "MV60"
    assert normalise_category("V70", "Female") == "WV70"

    # Already valid codes
    assert normalise_category("MV40", "Male") == "MV40"
    assert normalise_category("SW", "Female") == "SW"

    # Unknown category falls back to stripped original
    assert normalise_category("SuperVeteran", "Male") == "SuperVeteran"


def test_update_sync_settings_caps_at_24_hours(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date=datetime(2026, 3, 1, tzinfo=UTC).date(),
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
    )

    service = ResultsSyncService(test_db)

    # Test setting 48 hours is capped to MAX_AUTO_SYNC_HOURS (24)
    before = datetime.now(UTC)
    updated = service.update_sync_settings(
        fixture_id=fixture.id,
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
        auto_sync_enabled=True,
        auto_sync_hours=48,
        auto_sync_interval_minutes=15,
    )
    after = datetime.now(UTC)

    assert updated.auto_sync_enabled is True
    assert (
        updated.tempo_results_url
        == "https://www.racetecresults.com/results.aspx?CId=16418&RId=1006"
    )
    assert updated.auto_sync_interval_minutes == 15
    assert updated.auto_sync_until is not None

    # Verify auto_sync_until is within [now + 24h - 5s, now + 24h + 5s]
    expected_max = after + timedelta(hours=MAX_AUTO_SYNC_HOURS)
    expected_min = before + timedelta(hours=MAX_AUTO_SYNC_HOURS)
    auto_until_utc = (
        updated.auto_sync_until.astimezone(UTC)
        if updated.auto_sync_until.tzinfo is None
        else updated.auto_sync_until.astimezone(UTC)
    )
    assert (
        expected_min - timedelta(seconds=2)
        <= auto_until_utc
        <= expected_max + timedelta(seconds=2)
    )


def test_ingest_parsed_races_and_standings(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date=datetime(2026, 3, 1, tzinfo=UTC).date(),
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
    )

    parsed_race = ParsedRaceWithResults(
        race_name="Senior Men's Race",
        results=[
            ParsedResult(
                position=1,
                race_number=1188,
                athlete_name="Ben Cole",
                time="00:27:10",
                category="V40",
                category_position=1,
                gender="Male",
                gender_position=1,
                club="Swindon Harriers",
            ),
            ParsedResult(
                position=2,
                race_number=1789,
                athlete_name="Alex Bampton",
                time="00:27:24",
                category="Senior Men",
                category_position=1,
                gender="Male",
                gender_position=2,
                club="Swindon Harriers",
            ),
        ],
    )

    service = ResultsSyncService(test_db)
    summary = service.ingest_parsed_races(fixture, [parsed_race])

    assert summary.success is True
    assert summary.races_synced == 1
    assert summary.finishers_synced == 2
    assert "Senior Men's Race" in summary.races

    # Verify DuckDB persisted race and results
    races = repository.list_races_for_fixture(test_db, fixture.id)
    assert len(races) == 1
    assert races[0].name == "Senior Men's Race"

    results = repository.list_results_for_race(test_db, races[0].id)
    assert len(results) == 2
    assert results[0].position == 1
    assert results[0].athlete_name == "Ben Cole"
    assert results[0].category == "MV40"  # Normalized!
    assert results[1].position == 2
    assert results[1].category == "SM"  # Normalized!

    # Idempotent re-sync with updated finish order
    updated_parsed = ParsedRaceWithResults(
        race_name="Senior Men's Race",
        results=[
            ParsedResult(
                position=1,
                race_number=1789,
                athlete_name="Alex Bampton",
                time="00:27:00",
                category="Senior Men",
                category_position=1,
                gender="Male",
                gender_position=1,
                club="Swindon Harriers",
            ),
        ],
    )
    summary2 = service.ingest_parsed_races(fixture, [updated_parsed])
    assert summary2.finishers_synced == 1

    results_after = repository.list_results_for_race(test_db, races[0].id)
    assert len(results_after) == 1
    assert results_after[0].athlete_name == "Alex Bampton"


def test_ingest_empty_race_results_preserves_existing_results(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date="2026-03-01",
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
    )
    service = ResultsSyncService(test_db)
    existing_race = ParsedRaceWithResults(
        race_name="Senior Men's Race",
        results=[
            ParsedResult(
                position=1,
                athlete_name="Ben Cole",
                time="00:27:10",
                category="SM",
            )
        ],
    )
    assert service.ingest_parsed_races(fixture, [existing_race]).success

    empty_update = service.ingest_parsed_races(
        fixture,
        [ParsedRaceWithResults(race_name="Senior Men's Race", results=[])],
    )

    assert empty_update.success is False
    assert "existing results were not changed" in (empty_update.error or "")
    race = repository.get_race_by_name(test_db, fixture.id, "Senior Men's Race")
    assert race is not None
    results = repository.list_results_for_race(test_db, race.id)
    assert len(results) == 1
    assert results[0].athlete_name == "Ben Cole"


def test_ingest_csv_fallback(test_db: duckdb.DuckDBPyConnection) -> None:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 1",
        date=datetime(2025, 11, 2, tzinfo=UTC).date(),
        location_name="Horspath",
        address="Oxford",
        timetable=[],
        travel_instructions="",
    )

    csv_data = """Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club
1,501,Alice Walker,00:25:30,Senior Women,1,Female,1,Oxford City AC
2,502,Beth Davis,00:26:15,V40,1,Female,2,Headington RR
"""
    service = ResultsSyncService(test_db)
    summary = service.ingest_csv(fixture.id, "Senior Women's Race", csv_data)

    assert summary.success is True
    assert summary.finishers_synced == 2

    races = repository.list_races_for_fixture(test_db, fixture.id)
    assert len(races) == 1
    assert races[0].name == "Senior Women's Race"

    results = repository.list_results_for_race(test_db, races[0].id)
    assert len(results) == 2
    assert results[0].athlete_name == "Alice Walker"
    assert results[0].category == "SW"
    assert results[1].athlete_name == "Beth Davis"
    assert results[1].category == "WV40"


@pytest.mark.asyncio
async def test_check_and_run_due_syncs_expiration(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2025-2026")
    past_until = datetime.now(UTC) - timedelta(hours=1)
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Past Fixture",
        date=datetime(2025, 11, 2, tzinfo=UTC).date(),
        location_name="Horspath",
        address="Oxford",
        timetable=[],
        travel_instructions="",
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
    )
    repository.update_fixture_sync_settings(
        test_db,
        fixture_id=fixture.id,
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
        auto_sync_enabled=True,
        auto_sync_until=past_until,
        auto_sync_interval_minutes=15,
    )

    service = ResultsSyncService(test_db)
    # The fixture's auto_sync_until has expired; running due syncs should deactivate it
    summaries = await service.check_and_run_due_syncs()
    assert len(summaries) == 0

    reloaded = repository.get_fixture_by_id(test_db, fixture.id)
    assert reloaded is not None
    assert reloaded.auto_sync_enabled is False


@pytest.mark.asyncio
async def test_failed_auto_sync_respects_configured_interval(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date="2026-03-01",
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
    )
    repository.update_fixture_sync_settings(
        test_db,
        fixture_id=fixture.id,
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=1&RId=2",
        auto_sync_enabled=True,
        auto_sync_until=datetime.now(UTC) + timedelta(hours=1),
        auto_sync_interval_minutes=15,
    )
    service = ResultsSyncService(test_db)

    with patch(
        "website.services.results_sync.scrape_racetec_results",
        new_callable=AsyncMock,
        side_effect=RaceTecScrapeError("temporarily unavailable"),
    ) as scrape:
        first = await service.check_and_run_due_syncs()
        second = await service.check_and_run_due_syncs()

    assert len(first) == 1
    assert first[0].success is False
    assert second == []
    assert scrape.await_count == 1
    reloaded = repository.get_fixture_by_id(test_db, fixture.id)
    assert reloaded is not None
    assert reloaded.last_synced_at is None
    assert reloaded.last_sync_attempt_at is not None
