import sys

sys.path.insert(0, "scripts")
from migrate_results import _parse_per_page_pdf
from pathlib import Path

fp = Path(
    "data/original_website/files/results/2010-2020/2019-2020/20191103-Rnd1-BicesterHeritage-min.pdf"
)
races = _parse_per_page_pdf(fp)
print(f"2019-2020 Rnd1: {len(races)} races")
for race in races:
    print(f"  Race: {race['name']!r}, {len(race['results'])} results")
    for r in race["results"][:2]:
        print(
            f"    {r['position']}. {r['athlete_name']} | {r['club']} | {r['category']} | {r['gender']} | {r['time']}"
        )
