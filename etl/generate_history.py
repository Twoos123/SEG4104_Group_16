"""Generate a synthetic 'legacy 311 export' CSV.

No real city data is used. The file is deliberately messy (mixed date formats, inconsistent
category labels, personal details in free text, exact duplicates, blank rows) so the ETL job has
real cleaning work to do, and a share of rows are vague or mislabelled so the classifier is not
tested on unrealistically easy data.
"""

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db  # noqa: E402

PHRASES = {
    "pothole": [
        "deep pothole in the right lane",
        "huge pothole, cars are swerving around it",
        "pot hole damaged my tire",
        "crater in the road keeps getting bigger",
        "big hole in the pavement near the bus stop",
        "road surface is broken up with holes",
        "hit a pothole and bent my rim",
        "asphalt has caved in a bit in the curb lane",
    ],
    "sidewalk_damage": [
        "sidewalk slab is lifted and people are tripping",
        "cracked sidewalk outside the school",
        "broken sidewalk panel, wheelchair cannot pass",
        "uneven sidewalk, my mother fell",
        "sidewalk concrete is crumbling",
        "trip hazard on the walkway, slab sticking up",
        "curb is broken at the crosswalk ramp",
        "walkway pavement heaved up",
    ],
    "snow_removal": [
        "street has not been plowed since the storm",
        "sidewalk is a sheet of ice",
        "snowbank blocking the bus stop",
        "plow left a windrow across my driveway",
        "no salt on the hill, cars sliding",
        "sidewalk plow skipped our block",
        "icy road needs sanding",
        "snow piled so high we cannot see at the corner",
    ],
    "missed_garbage": [
        "garbage was not picked up today",
        "recycling bin was skipped again",
        "green bin not collected on our street",
        "truck missed the whole block",
        "my trash is still at the curb from tuesday",
        "blue box was left full",
        "yard waste bags were not taken",
        "collection crew skipped my house",
    ],
    "illegal_dumping": [
        "someone dumped a couch in the alley",
        "pile of construction debris left on the boulevard",
        "mattresses dumped behind the plaza",
        "bags of trash thrown in the ditch",
        "old tires dumped at the dead end",
        "contractor left a load of drywall on city land",
        "furniture abandoned on the roadside",
        "someone keeps dumping garbage in the laneway",
    ],
    "streetlight_out": [
        "streetlight is out in front of my house",
        "street lamp has been flickering for weeks",
        "three lights in a row are dark",
        "light pole lamp burned out, very dark at night",
        "streetlight stays on all day",
        "lamp post light not working near the park path",
        "the street is pitch black, light is dead",
        "streetlight buzzing and cutting out",
    ],
    "traffic_signal": [
        "traffic light is stuck on red",
        "signal is flashing red in all directions",
        "pedestrian walk signal does not work",
        "left turn arrow never comes on",
        "traffic lights are completely out at the intersection",
        "signal timing is way off, long backups",
        "crosswalk button is broken",
        "light is green both ways",
    ],
    "fallen_tree": [
        "large branch fell and is blocking the sidewalk",
        "tree came down across the road",
        "city tree split in the wind",
        "big limb hanging over the street, about to fall",
        "tree fell on a parked car",
        "branches down all over the bike path",
        "dead tree leaning toward the road",
        "storm knocked a tree onto the boulevard",
    ],
    "park_maintenance": [
        "playground swing is broken",
        "grass in the park has not been cut in weeks",
        "park bench is smashed",
        "garbage cans in the park are overflowing",
        "splash pad is not working",
        "soccer field is full of ruts",
        "picnic table broken in the park",
        "park washroom is locked during open hours",
    ],
    "graffiti": [
        "graffiti sprayed on the underpass",
        "offensive tag on the bus shelter",
        "someone spray painted the community centre wall",
        "graffiti all over the utility box",
        "tags on the bridge railing",
        "vandals painted the park sign",
        "spray paint on the retaining wall",
        "hateful graffiti on the fence by the path",
    ],
    "noise_complaint": [
        "neighbour playing loud music at 2am",
        "construction noise before 6 in the morning",
        "dog barking all night next door",
        "party with loud bass every weekend",
        "leaf blower running at dawn",
        "bar patio noise late at night",
        "car alarm going off for hours",
        "loud renovation work on sunday night",
    ],
    "water_leak": [
        "water is bubbling up through the pavement",
        "water main break, street is wet",
        "water gushing from the hydrant",
        "steady stream of water running down the curb",
        "leak at the water valve cover",
        "low water pressure and water pooling on the road",
        "water coming out of the ground by the meter",
        "pipe burst, water spraying",
    ],
}

# Vague reports a real agent would also struggle with (true label, text)
AMBIGUOUS = [
    ("pothole", "the road is in terrible shape here"),
    ("sidewalk_damage", "something is broken on the path"),
    ("streetlight_out", "it is really dark on this street"),
    ("traffic_signal", "the light is not working"),
    ("streetlight_out", "the light is not working"),
    ("fallen_tree", "mess left after the storm"),
    ("snow_removal", "mess left after the storm"),
    ("missed_garbage", "garbage everywhere on our street"),
    ("illegal_dumping", "garbage everywhere on our street"),
    ("park_maintenance", "garbage piling up near the park"),
    ("illegal_dumping", "garbage piling up near the park"),
    ("water_leak", "big puddle that never dries"),
    ("pothole", "big puddle that never dries"),
    ("noise_complaint", "city crew making a racket"),
    ("graffiti", "vandalism at the park"),
    ("park_maintenance", "vandalism at the park"),
    ("snow_removal", "cannot get down the sidewalk safely"),
    ("sidewalk_damage", "cannot get down the sidewalk safely"),
    ("fallen_tree", "branch knocked out the lamp"),
    ("streetlight_out", "branch knocked out the lamp"),
]
OPENERS = [
    "",
    "",
    "",
    "Hi, ",
    "Hello, ",
    "Reporting that ",
    "Just so you know ",
    "Please fix: ",
    "Third time reporting this - ",
    "Urgent - ",
    "FYI ",
    "To whom it may concern, ",
]
TAILS = [
    "",
    "",
    "",
    " Please send someone.",
    " It has been like this for days.",
    " Thanks.",
    " This is dangerous.",
    " Kids walk here.",
    " Not acceptable.",
    " When will this be fixed?",
]
PII = [
    " Call me at 613-555-01{:02d}.",
    " My email is resident{:02d}@example.com.",
    " My name is Alex Morgan, reach me at (613) 555-01{:02d}.",
    " text 613.555.01{:02d} with updates",
]
LABELS = {  # how each category was typed in the legacy system
    "pothole": ["Pothole", "POTHOLE", "pot hole", "Pothole Repair"],
    "sidewalk_damage": ["Sidewalk Damage", "sidewalk", "Sidewalk - Repair"],
    "snow_removal": ["Snow Removal", "SNOW/ICE", "snow & ice"],
    "missed_garbage": ["Missed Garbage", "Missed Collection", "garbage - missed"],
    "illegal_dumping": ["Illegal Dumping", "DUMPING", "Dumping (illegal)"],
    "streetlight_out": ["Streetlight Out", "Street Light", "streetlight"],
    "traffic_signal": ["Traffic Signal", "TRAFFIC LIGHT", "Signal Problem"],
    "fallen_tree": ["Fallen Tree", "Tree Down", "tree/branch"],
    "park_maintenance": ["Park Maintenance", "PARKS", "Parks - Maintenance"],
    "graffiti": ["Graffiti", "GRAFFITI", "graffiti removal"],
    "noise_complaint": ["Noise Complaint", "NOISE", "Noise"],
    "water_leak": ["Water Leak", "Water Main", "WATER - LEAK"],
}
SEASON = {
    "snow_removal": [12, 1, 2, 3],
    "pothole": [3, 4, 5],
    "fallen_tree": [6, 7, 8, 10],
    "park_maintenance": [5, 6, 7, 8, 9],
    "noise_complaint": [5, 6, 7, 8, 9],
}
DATE_FORMATS = ["%Y-%m-%d %H:%M", "%m/%d/%Y %I:%M %p", "%d-%b-%Y %H:%M"]
CHANNELS, CHANNEL_WEIGHTS = ["phone", "web", "email"], [5, 3, 2]


def typo(text: str, rng: random.Random) -> str:
    if len(text) < 12:
        return text
    i = rng.randrange(3, len(text) - 3)
    return text[:i] + text[i + 1 :]


def pick_category(rng: random.Random, month: int) -> str:
    cats = list(PHRASES)
    weights = [3.0 if month in SEASON.get(c, []) else (0.15 if c == "snow_removal" else 1.0) for c in cats]
    return rng.choices(cats, weights)[0]


def noisy_text(rng: random.Random, body: str) -> str:
    """Wrap a problem description the way residents actually write: greetings, contact details, typos."""
    text = rng.choice(OPENERS) + body + rng.choice(TAILS)
    if rng.random() < 0.15:
        text += rng.choice(PII).format(rng.randrange(100))
    if rng.random() < 0.12:
        text = typo(text, rng)
    if rng.random() < 0.10:
        text = text.upper() if rng.random() < 0.3 else text.lower()
    return text


def corrupt(rng: random.Random, row: dict) -> dict:
    """Break a small share of rows the way a legacy export does (blank text, junk label, bad date)."""
    roll = rng.random()
    if roll < 0.010:
        row["description"] = ""
    elif roll < 0.020:
        row["type"] = rng.choice(["Other", "???", "General Inquiry"])
    elif roll < 0.025:
        row["received"] = rng.choice(["n/a", "00/00/0000", ""])
    return row


def repeat_reports(rng: random.Random, cat: str, when: datetime, address: str) -> list[dict]:
    """The same problem is often reported again by other residents over the next few days."""
    rows = []
    for _ in range(rng.randrange(1, 7)):
        again = when + timedelta(minutes=rng.randrange(30, 5 * 24 * 60))
        rows.append(
            {
                "received": again.strftime(rng.choice(DATE_FORMATS)),
                "channel": rng.choices(CHANNELS, CHANNEL_WEIGHTS)[0],
                "type": rng.choice(LABELS[cat]),
                "description": rng.choice(OPENERS) + rng.choice(PHRASES[cat]) + rng.choice(TAILS),
                "location": address,
            }
        )
    return rows


def generate(n: int = 5400, seed: int = 4105) -> list[dict]:
    rng = random.Random(seed)  # nosec B311 - synthetic test data, not a security use
    streets = [s[0] for s in db.STREETS]
    start = datetime(2024, 11, 1)
    rows = []
    for _ in range(n):
        when = start + timedelta(minutes=rng.randrange(0, 730 * 24 * 60))
        cat = pick_category(rng, when.month)
        body = rng.choice(PHRASES[cat])
        if rng.random() < 0.08:
            cat, body = rng.choice(AMBIGUOUS)
        # 3% of the time the legacy agent filed the request under the wrong category
        label_cat = rng.choice(list(PHRASES)) if rng.random() < 0.03 else cat
        address = f"{rng.randrange(1, 900)} {rng.choice(streets)}"
        if rng.random() < 0.03:
            address = rng.choice(["", "near the mall", "corner by the school", "unknown"])
        rows.append(
            corrupt(
                rng,
                {
                    "received": when.strftime(rng.choice(DATE_FORMATS)),
                    "channel": rng.choices(CHANNELS, CHANNEL_WEIGHTS)[0],
                    "type": rng.choice(LABELS[label_cat]),
                    "description": noisy_text(rng, body),
                    "location": address,
                },
            )
        )
        if address[:1].isdigit() and cat != "noise_complaint" and rng.random() < 0.05:
            rows.extend(repeat_reports(rng, cat, when, address))
    for _ in range(int(n * 0.02)):  # the legacy system exported some rows twice
        rows.insert(rng.randrange(len(rows)), dict(rng.choice(rows)))
    return rows


def main(out: Path | None = None) -> Path:
    out = out or config.DATA_DIR / "legacy_311_export.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = generate()
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")
    return out


if __name__ == "__main__":
    main()
