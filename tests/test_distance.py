import pytest
import requests
from alcana_bot.distance import geocode_address, haversine_km, estimate_driving_km, DistanceError

SAMPLE_GEOCODE_RESPONSE = {
    "status": "OK",
    "results": [
        {"geometry": {"location": {"lat": 41.311081, "lng": 69.240562}}}
    ],
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
    mock_get.return_value.json.return_value = {"status": "ZERO_RESULTS", "results": []}
    mock_get.return_value.raise_for_status = lambda: None

    with pytest.raises(DistanceError, match="ZERO_RESULTS"):
        geocode_address("nonexistent place asdkjashd", api_key="fake-key")

def test_geocode_address_non_ok_status_raises(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.json.return_value = {"status": "REQUEST_DENIED", "results": []}
    mock_get.return_value.raise_for_status = lambda: None

    with pytest.raises(DistanceError, match="REQUEST_DENIED"):
        geocode_address("Chilonzor, Tashkent", api_key="bad-key")

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

def test_geocode_address_http_error_raises_distance_error(mocker):
    """Verify that HTTP errors are converted to DistanceError, not propagated raw."""
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    with pytest.raises(DistanceError, match="Geocoding .* failed"):
        geocode_address("Chilonzor, Tashkent", api_key="fake-key")

def test_geocode_address_error_never_leaks_api_key(mocker):
    """requests' HTTPError message embeds the full URL incl. ?key=<secret>."""
    secret = "SUPER-SECRET-GOOGLE-KEY"
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
        f"403 Client Error: Forbidden for url: "
        f"https://maps.googleapis.com/maps/api/geocode/json?address=Chilonzor&key={secret}"
    )

    with pytest.raises(DistanceError) as excinfo:
        geocode_address("Chilonzor, Tashkent", api_key=secret)

    assert secret not in str(excinfo.value)
    assert "key=" not in str(excinfo.value)
    assert "HTTPError" in str(excinfo.value)

def test_geocode_address_error_includes_status_code_when_available(mocker):
    mock_get = mocker.patch("alcana_bot.distance.requests.get")
    error = requests.exceptions.HTTPError("403 Client Error for url: https://x/?key=secret")
    error.response = mocker.Mock(status_code=403)
    mock_get.return_value.raise_for_status.side_effect = error

    with pytest.raises(DistanceError, match="HTTP 403"):
        geocode_address("Chilonzor, Tashkent", api_key="secret")
