import pytest
from alcana_bot.distance import geocode_address, haversine_km, estimate_driving_km, DistanceError

SAMPLE_GEOCODE_RESPONSE = {
    "response": {
        "GeoObjectCollection": {
            "featureMember": [
                {"GeoObject": {"Point": {"pos": "69.240562 41.311081"}}}
            ]
        }
    }
}

def test_geocode_address_parses_lat_lon(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.json.return_value = SAMPLE_GEOCODE_RESPONSE
    mock_get.return_value.raise_for_status = lambda: None

    lat, lon = geocode_address("Chilonzor, Tashkent", api_key="fake-key")

    assert lat == pytest.approx(41.311081)
    assert lon == pytest.approx(69.240562)

def test_geocode_address_no_results_raises(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.json.return_value = {"response": {"GeoObjectCollection": {"featureMember": []}}}
    mock_get.return_value.raise_for_status = lambda: None

    with pytest.raises(DistanceError, match="no results"):
        geocode_address("nonexistent place asdkjashd", api_key="fake-key")

def test_haversine_km_known_distance():
    # Workshop origin to a point ~2km away (rough check, not exact)
    workshop = (41.291234, 69.196435)
    nearby = (41.30, 69.20)
    km = haversine_km(workshop, nearby)
    assert 0.5 < km < 3.0

def test_estimate_driving_km_applies_road_factor():
    origin = (41.291234, 69.196435)
    destination = (41.30, 69.20)
    straight = haversine_km(origin, destination)
    driving = estimate_driving_km(origin, destination)
    assert driving == pytest.approx(straight * 1.3, rel=1e-6)
