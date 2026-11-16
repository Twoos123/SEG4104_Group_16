"""Geocoding and distance. The street table stands in for the city GIS service."""

import math
import re
from dataclasses import dataclass

ADDRESS = re.compile(r"^\s*(\d{1,5})\s+(.+?)\s*$")
_ABBREV = {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd"}
METRES_PER_HOUSE_NUMBER = 1.1
_DEG_LAT_PER_M = 1 / 111_320


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    ward_id: int
    street: str


def _normalise(street: str) -> str:
    words = re.sub(r"[.,]", "", street.lower()).split()
    return " ".join(_ABBREV.get(w, w) for w in words)


def geocode(conn, address: str | None) -> Location | None:
    """Turn '123 Bank St' into coordinates and a ward, or None if it cannot be resolved."""
    if not address:
        return None
    m = ADDRESS.match(address)
    if not m:
        return None
    number, street = int(m.group(1)), _normalise(m.group(2))
    for row in conn.execute("SELECT name, ward_id, base_lat, base_lon FROM street"):
        if _normalise(row["name"]) == street:
            lat = row["base_lat"] + number * METRES_PER_HOUSE_NUMBER * _DEG_LAT_PER_M
            return Location(round(lat, 6), row["base_lon"], row["ward_id"], row["name"])
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
