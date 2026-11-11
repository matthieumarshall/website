"""Round changes are rolled back when copying fails."""

import json
from unittest.mock import Mock

import pytest

from website import repository
from website.errors import ConflictError, ValidationError
from website.models import TimetableEntry
from website.models.forms import FixtureForm
from website.repository.fixtures import replace_timetable_items
from website.services.fixtures import FixtureService
from website.services.uploads import IMAGE_POLICY, FileStore


def setup_round(db, tmp_path):
    season = repository.create_season(db, "2025")
    source = repository.create_fixture(
        db, season.id, "Source", "2025-09-01", "V", "A", [], ""
    )
    race = repository.create_race(db, source.id, "Under 13")
    replace_timetable_items(
        db, source.id, [TimetableEntry(time="10:00", event="Start", race_id=race.id)]
    )
    store = FileStore(tmp_path, IMAGE_POLICY)
    filename = store.save_bytes(b"image", ".png")
    repository.create_fixture_image(db, source.id, filename)
    service = FixtureService(db, Mock(), store)
    return season, source, service


def form_for(service, source, title):
    prefill = service.prefill_from(source.id, ["timetable", "races"])
    return FixtureForm(
        title=title,
        date="2025-10-01",
        location_name="V",
        address="A",
        latitude="51",
        longitude="-1",
        timetable_json=json.dumps([e.model_dump() for e in prefill.timetable]),
        copy_from_fixture_id=source.id,
        copy_races=True,
        copy_maps=True,
    )


def test_create_rolls_back_round_races_and_copied_files(test_db, tmp_path, monkeypatch):
    season, source, service = setup_round(test_db, tmp_path)
    original = service._copy_races

    def fail_after_copy(source_id, target_id):
        original(source_id, target_id)
        raise RuntimeError("race copy failed")

    monkeypatch.setattr(service, "_copy_races", fail_after_copy)
    before = set(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="race copy failed"):
        service.create_fixture(season.id, form_for(service, source, "Copy"))
    assert [f.id for f in repository.list_fixtures_for_season(test_db, season.id)] == [
        source.id
    ]
    assert set(tmp_path.iterdir()) == before


def test_edit_rolls_back_details_schedule_races_and_copied_files(
    test_db, tmp_path, monkeypatch
):
    season, source, service = setup_round(test_db, tmp_path)
    target = repository.create_fixture(
        test_db,
        season.id,
        "Target",
        "2025-10-01",
        "V",
        "A",
        [TimetableEntry(time="09:00", event="Original")],
        "",
    )
    original = service._copy_races

    def fail_after_copy(source_id, target_id):
        original(source_id, target_id)
        raise RuntimeError("race copy failed")

    monkeypatch.setattr(service, "_copy_races", fail_after_copy)
    before = set(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="race copy failed"):
        service.update_fixture(target.id, form_for(service, source, "Changed"))
    restored = repository.get_fixture_by_id(test_db, target.id)
    assert restored is not None
    assert restored.title == "Target"
    assert [(entry.time, entry.event) for entry in restored.timetable] == [
        ("09:00", "Original")
    ]
    assert repository.list_races_for_fixture(test_db, target.id) == []
    assert repository.list_fixture_images(test_db, target.id) == []
    assert set(tmp_path.iterdir()) == before


def test_failed_image_record_removes_file_and_rolls_back_round(
    test_db, tmp_path, monkeypatch
):
    season, source, service = setup_round(test_db, tmp_path)
    before = set(tmp_path.iterdir())

    def fail_image_record(*args, **kwargs):
        raise RuntimeError("image record failed")

    monkeypatch.setattr(repository, "create_fixture_image", fail_image_record)
    with pytest.raises(RuntimeError, match="image record failed"):
        service.create_fixture(season.id, form_for(service, source, "Copy"))
    assert [f.id for f in repository.list_fixtures_for_season(test_db, season.id)] == [
        source.id
    ]
    assert set(tmp_path.iterdir()) == before


def test_failed_file_copy_removes_partial_output(tmp_path, monkeypatch):
    store = FileStore(tmp_path, IMAGE_POLICY)
    source = store.save_bytes(b"image", ".png")
    before = set(tmp_path.iterdir())

    def fail_copy(src, target):
        target.write_bytes(b"partial")
        raise OSError("copy failed")

    monkeypatch.setattr("website.services.uploads.shutil.copyfile", fail_copy)
    with pytest.raises(OSError, match="copy failed"):
        store.copy(source)
    assert set(tmp_path.iterdir()) == before


def test_edit_returns_saved_round_with_copied_race_links(test_db, tmp_path):
    season, source, service = setup_round(test_db, tmp_path)
    target = repository.create_fixture(
        test_db, season.id, "Target", "2025-10-01", "V", "A", [], ""
    )
    updated = service.update_fixture(target.id, form_for(service, source, "Changed"))
    races = repository.list_races_for_fixture(test_db, target.id)
    assert updated.title == "Changed"
    assert len(races) == 1
    assert updated.timetable[0].race_id == races[0].id
    assert len(repository.list_fixture_images(test_db, target.id)) == 1


def test_edit_rejects_race_from_another_round_without_changing_target(
    test_db, tmp_path
):
    season, source, service = setup_round(test_db, tmp_path)
    target = repository.create_fixture(
        test_db, season.id, "Target", "2025-10-01", "V", "A", [], ""
    )
    source_race = repository.list_races_for_fixture(test_db, source.id)[0]
    form = form_for(service, source, "Changed")
    form.copy_races = False
    form.copy_maps = False
    form.timetable_json = json.dumps(
        [{"time": "10:00", "event": "Start", "race_id": source_race.id}]
    )
    with pytest.raises(ValidationError, match="belong"):
        service.update_fixture(target.id, form)
    restored = repository.get_fixture_by_id(test_db, target.id)
    assert restored is not None
    assert restored.title == "Target"


def test_copy_selected_round_parts_into_existing_round(test_db, tmp_path):
    season, source, service = setup_round(test_db, tmp_path)
    target = repository.create_fixture(
        test_db,
        season.id,
        "Target",
        "2025-10-01",
        "Old venue",
        "Old address",
        [],
        "Old travel",
    )
    copied = service.copy_parts_into(
        target.id, source.id, ["location", "timetable", "travel"]
    )
    assert copied.location_name == source.location_name
    assert copied.address == source.address
    assert copied.travel_instructions == source.travel_instructions
    assert copied.timetable[0].race_id is None
    assert (
        copied.timetable[0].source_race_id
        == repository.list_races_for_fixture(test_db, source.id)[0].id
    )
    assert (
        service.copy_parts_into(target.id, source.id, []).location_name == "Old venue"
    )


def test_round_with_results_cannot_be_deleted_even_after_confirmation(
    test_db, tmp_path
):
    _, source, service = setup_round(test_db, tmp_path)
    race = repository.list_races_for_fixture(test_db, source.id)[0]
    repository.create_result(
        test_db, race.id, 1, "Runner", "30:00", "U13B", "M", club="AC"
    )
    with pytest.raises(ConflictError, match="Confirm"):
        service.delete_fixture(source.id)
    with pytest.raises(ConflictError, match="not yet supported"):
        service.delete_fixture(source.id, confirmed=True)
    assert repository.get_fixture_by_id(test_db, source.id) is not None
