from __future__ import annotations

from app.models.place import Place, PlaceAvailabilityRule, PlaceVisitProfile
from app.models.trip import Trip, TripCandidate


def add_place(
    db,
    *,
    name: str,
    lat: float = 35.05,
    lng: float = 139.9,
    category: str = "cafe",
    tags: list[str] | None = None,
    traits: list[str] | None = None,
    stay_min_minutes: int = 30,
    stay_preferred_minutes: int = 45,
    stay_max_minutes: int = 90,
) -> Place:
    place = Place(
        name=name,
        lat=lat,
        lng=lng,
        source="manual",
        archived=False,
        category=category,
        tags_json=list(tags or []),
        traits_json=list(traits or []),
        notes=None,
    )
    db.add(place)
    db.flush()
    db.add(
        PlaceVisitProfile(
            place_id=place.id,
            stay_min_minutes=stay_min_minutes,
            stay_preferred_minutes=stay_preferred_minutes,
            stay_max_minutes=stay_max_minutes,
            price_band=None,
            rating=4.2,
            accessibility_notes=None,
        )
    )
    db.add(
        PlaceAvailabilityRule(
            place_id=place.id,
            weekday=None,
            open_minute=9 * 60,
            close_minute=20 * 60,
            valid_from=None,
            valid_to=None,
            last_admission_minute=None,
            closed_flag=False,
        )
    )
    db.commit()
    db.refresh(place)
    return place


def add_candidate(db, *, trip: Trip, place: Place, priority: str = "normal") -> TripCandidate:
    candidate = TripCandidate(
        trip_id=trip.id,
        place_id=place.id,
        candidate_state="active",
        priority=priority,
        locked_in=False,
        locked_out=False,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate
