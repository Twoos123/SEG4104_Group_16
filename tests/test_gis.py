import pytest

from app import gis


def test_geocode_known_street(conn):
    loc = gis.geocode(conn, "245 Bank St")
    assert loc is not None and loc.street == "Bank St" and loc.ward_id == 2
    assert 45.0 < loc.lat < 46.0


@pytest.mark.parametrize("address", ["245 bank street", "245 BANK ST.", "  245 Bank St  "])
def test_geocode_normalises_spelling(conn, address):
    assert gis.geocode(conn, address).street == "Bank St"


@pytest.mark.parametrize("address", [None, "", "near the mall", "245 Nowhere Rd", "Bank St"])
def test_geocode_unknown_returns_none(conn, address):
    assert gis.geocode(conn, address) is None


def test_house_numbers_map_to_distance(conn):
    a, b, c = (gis.geocode(conn, f"{n} Bank St") for n in (100, 110, 300))
    assert gis.haversine_m(a.lat, a.lon, b.lat, b.lon) == pytest.approx(11, abs=1)
    assert gis.haversine_m(a.lat, a.lon, c.lat, c.lon) == pytest.approx(220, abs=3)


def test_haversine_zero_and_known_distance():
    assert gis.haversine_m(45.4, -75.7, 45.4, -75.7) == 0
    assert gis.haversine_m(45.0, -75.0, 46.0, -75.0) == pytest.approx(111_195, rel=0.01)
