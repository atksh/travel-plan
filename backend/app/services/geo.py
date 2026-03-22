"""Geographic helpers."""

from math import asin, cos, radians, sin, sqrt

EARTH_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometers."""
    rlat1, rlng1, rlat2, rlng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    return EARTH_KM * c


def estimate_drive_minutes(
    lat1: float, lng1: float, lat2: float, lng2: float, kmh: float = 58.0
) -> int:
    """Rough drive time from straight-line distance and average speed."""
    dist_km = haversine_km(lat1, lng1, lat2, lng2)
    minutes = int(round((dist_km / kmh) * 60))
    return max(5, minutes)
