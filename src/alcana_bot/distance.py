import math
import requests

class DistanceError(Exception):
    pass

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

def geocode_address(address: str, api_key: str) -> tuple[float, float]:
    try:
        response = requests.get(GEOCODE_URL, params={
            "address": address,
            "key": api_key,
        }, timeout=10)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status != "OK":
            raise DistanceError(f"Geocoding '{address}' returned status {status}")
        location = data["results"][0]["geometry"]["location"]
        return float(location["lat"]), float(location["lng"])
    except DistanceError:
        raise
    except requests.exceptions.RequestException as e:
        # NEVER interpolate this exception: requests embeds the full prepared
        # URL (including ?key=<secret>) in HTTPError's message, and the
        # resulting DistanceError text gets logged by the bot handlers.
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        status_part = f" (HTTP {status_code})" if status_code is not None else ""
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
