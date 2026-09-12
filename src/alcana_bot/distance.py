import math
import requests

class DistanceError(Exception):
    pass

GEOCODE_URL = "https://geocode-maps.yandex.ru/1.x/"

def geocode_address(address: str, api_key: str) -> tuple[float, float]:
    try:
        response = requests.get(GEOCODE_URL, params={
            "apikey": api_key,
            "geocode": address,
            "format": "json",
            "results": 1,
        }, timeout=10)
        response.raise_for_status()
        data = response.json()
        members = data["response"]["GeoObjectCollection"]["featureMember"]
        if not members:
            raise DistanceError(f"Geocoding '{address}' returned no results")
        pos = members[0]["GeoObject"]["Point"]["pos"]  # "lon lat"
        lon_str, lat_str = pos.split(" ")
        return float(lat_str), float(lon_str)
    except DistanceError:
        raise
    except requests.exceptions.RequestException as e:
        # NEVER interpolate this exception: requests embeds the full prepared
        # URL (including ?apikey=<secret>) in HTTPError's message, and the
        # resulting DistanceError text gets logged by the bot handlers.
        status = getattr(getattr(e, "response", None), "status_code", None)
        status_part = f" (HTTP {status})" if status is not None else ""
        raise DistanceError(f"Geocoding '{address}' failed: {type(e).__name__}{status_part}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise DistanceError(f"Geocoding '{address}' failed: {e}") from e

def haversine_km(origin: tuple, destination: tuple) -> float:
    lat1, lon1 = origin
    lat2, lon2 = destination
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def estimate_driving_km(origin: tuple, destination: tuple, road_factor: float = 1.3) -> float:
    return haversine_km(origin, destination) * road_factor
