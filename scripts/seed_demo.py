"""Load a small, varied set of requests so the demo pages are not empty.

Run after the ETL and training steps:  python scripts/seed_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, pipeline  # noqa: E402
from app.classifier import LocalClassifier  # noqa: E402

REQUESTS = [
    ("There is a deep pothole in the right lane, cars are swerving around it", "245 Bank St", "WEB"),
    ("hit a pothole and bent my rim, please fix", "250 Bank St", "PHONE"),
    ("Huge pothole near the bus stop. My name is Alex Morgan, call 613-555-0142", "248 Bank St", "EMAIL"),
    ("Streetlight is out in front of my house, very dark at night", "88 Fifth Ave", "WEB"),
    ("garbage was not picked up today on our street", "412 Richmond Rd", "PHONE"),
    ("recycling bin was skipped again", "415 Richmond Rd", "WEB"),
    ("Tree came down across the road after the storm", "30 Island Park Dr", "PHONE"),
    ("neighbour playing loud music at 2am every weekend", "610 Somerset St", "WEB"),
    ("graffiti sprayed on the bus shelter", "120 Rideau St", "WEB"),
    ("traffic light is stuck on red and backing up traffic", "5 Innes Rd", "PHONE"),
    ("water is bubbling up through the pavement and running down the curb", "77 Smyth Rd", "WEB"),
    ("sidewalk slab is lifted and people are tripping", "300 Elgin St", "EMAIL"),
    ("playground swing is broken in the park", "55 Kanata Ave", "WEB"),
    ("someone dumped a couch and mattresses in the alley", "19 Heron Rd", "WEB"),
    ("street has not been plowed since the storm, sheet of ice", "702 Greenbank Rd", "PHONE"),
    ("I can smell gas near the sidewalk, there might be a gas leak", "14 Laurier Ave", "PHONE"),
    ("downed power line sparking on the road after the wind", "501 Carling Ave", "PHONE"),
    ("the light is not working", "66 Walkley Rd", "WEB"),
    ("something is wrong with the road by the school", "near the school", "PHONE"),
    ("big puddle that never dries", "140 Trim Rd", "WEB"),
]


def main() -> None:
    db.init_db()
    clf = LocalClassifier.load()
    with db.session() as conn:
        for text, address, channel in REQUESTS:
            result = pipeline.process_request(conn, clf, text, address, channel, "resident@example.com")
            print(
                f"{result['ticket']}  {result['status']:<13} {result['category'] or '-':<17} "
                f"{result['confidence']:.2f}  {text[:48]}"
            )
        print(pipeline.metrics(conn))


if __name__ == "__main__":
    main()
