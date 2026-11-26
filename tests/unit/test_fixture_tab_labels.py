"""Round tabs show concise labels without repeating default titles."""

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


def test_fixture_tab_labels() -> None:
    templates = Path(__file__).resolve().parents[2] / "templates"
    env = Environment(
        loader=FileSystemLoader(templates), autoescape=select_autoescape()
    )
    html = env.get_template("_fixtures_season_panel.html").render(
        selected_season=SimpleNamespace(id=1, name="Season"),
        fixtures=[
            SimpleNamespace(id=1, round_number=1, title=" Round 1 "),
            SimpleNamespace(id=2, round_number=2, title="Horspath"),
            SimpleNamespace(id=3, round_number=None, title="ROUND 3"),
        ],
        active_fixture=None,
    )

    assert 'aria-label="Round 1"' in html
    assert ">R1</button>" in html
    assert 'aria-label="Round 2: Horspath"' in html
    assert ">R2. Horspath</button>" in html
    assert 'aria-label="Round 3"' in html
    assert ">R3</button>" in html
