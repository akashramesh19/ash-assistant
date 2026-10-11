import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
IP_LOCATE_URL = "https://get.geojs.io/v1/ip/geo.json"

WEATHER_CODES = {
    0: "clear sky",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}

TOOL_DEFINITION = {
    "name": "get_weather",
    "description": (
        "Get the current weather. Omit location for the user's current "
        "location (detected automatically); pass it only when the user "
        "names a specific place."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name, e.g. 'Sydney' or 'Melbourne, AU'. Omit for current location.",
            },
        },
        "required": [],
    },
}


def _locate_by_ip() -> tuple[float, float, str] | None:
    try:
        response = requests.get(IP_LOCATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return float(data["latitude"]), float(data["longitude"]), data.get("city", "your location")
    except requests.RequestException:
        return None


def _geocode(location: str) -> tuple[float, float, str]:
    response = requests.get(GEOCODE_URL, params={"name": location, "count": 1}, timeout=10)
    response.raise_for_status()
    results = response.json().get("results")
    if not results:
        return None
    place = results[0]
    return place["latitude"], place["longitude"], place.get("name", location)


def run(location: str = None, **kwargs) -> str:
    if location:
        resolved = _geocode(location)
        if resolved is None:
            return f"error: couldn't find a location matching '{location}'"
    else:
        resolved = _locate_by_ip()
        if resolved is None:
            return "error: couldn't detect current location — try naming a city instead"

    latitude, longitude, place_name = resolved

    forecast_response = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "temperature_unit": "celsius",
        },
        timeout=10,
    )
    forecast_response.raise_for_status()
    current = forecast_response.json()["current"]

    temperature = current["temperature_2m"]
    condition = WEATHER_CODES.get(current["weather_code"], "unknown conditions")

    return f"{place_name}: {temperature}°C, {condition}"
