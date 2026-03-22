"""Development-only sample places for the generalized planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.place import (
    Place,
    PlaceAvailabilityRule,
    PlaceSourceRecord,
    PlaceVisitProfile,
)


@dataclass(frozen=True)
class SeedPlaceSpec:
    name: str
    lat: float
    lng: float
    category: str
    tags: tuple[str, ...]
    traits: tuple[str, ...]
    stay_min: int
    stay_preferred: int
    stay_max: int
    open_min: int
    close_min: int
    price_band: str | None = None
    rating: float | None = None
    notes: str | None = None


SAMPLE_PLACES: tuple[SeedPlaceSpec, ...] = (
    SeedPlaceSpec(
        name="Seaside Cafe",
        lat=35.01,
        lng=139.84,
        category="cafe",
        tags=("scenic", "cafe"),
        traits=("indoor", "parking_available"),
        stay_min=30,
        stay_preferred=45,
        stay_max=90,
        open_min=9 * 60,
        close_min=18 * 60,
        price_band="moderate",
        rating=4.5,
    ),
    SeedPlaceSpec(
        name="Cliff Walk",
        lat=35.08,
        lng=139.91,
        category="viewpoint",
        tags=("scenic", "walk"),
        traits=("outdoor", "family_friendly"),
        stay_min=40,
        stay_preferred=60,
        stay_max=90,
        open_min=8 * 60,
        close_min=17 * 60,
        rating=4.3,
    ),
    SeedPlaceSpec(
        name="Harbor Market",
        lat=35.12,
        lng=139.88,
        category="market",
        tags=("local_food", "shopping"),
        traits=("indoor", "paid_entry"),
        stay_min=45,
        stay_preferred=60,
        stay_max=120,
        open_min=10 * 60,
        close_min=19 * 60,
        rating=4.1,
    ),
    SeedPlaceSpec(
        name="Garden Museum",
        lat=35.05,
        lng=139.95,
        category="museum",
        tags=("art", "quiet"),
        traits=("indoor", "accessible"),
        stay_min=60,
        stay_preferred=90,
        stay_max=150,
        open_min=10 * 60,
        close_min=17 * 60,
        price_band="moderate",
        rating=4.6,
    ),
    SeedPlaceSpec(
        name="Hot Spring Retreat",
        lat=35.18,
        lng=139.9,
        category="onsen",
        tags=("relax", "night"),
        traits=("indoor", "paid_entry", "parking_available"),
        stay_min=60,
        stay_preferred=120,
        stay_max=180,
        open_min=11 * 60,
        close_min=22 * 60,
        price_band="premium",
        rating=4.7,
    ),
    SeedPlaceSpec(
        name="Sunset Pier",
        lat=34.99,
        lng=139.86,
        category="pier",
        tags=("scenic", "sunset"),
        traits=("outdoor", "parking_available"),
        stay_min=20,
        stay_preferred=40,
        stay_max=60,
        open_min=0,
        close_min=24 * 60,
        rating=4.4,
    ),
)


def _upsert_place(session: Session, spec: SeedPlaceSpec) -> None:
    place = session.query(Place).filter(Place.name == spec.name, Place.source == "seed").one_or_none()
    if place is None:
        place = Place(
            name=spec.name,
            lat=spec.lat,
            lng=spec.lng,
            source="seed",
            archived=False,
            category=spec.category,
            tags_json=list(spec.tags),
            traits_json=list(spec.traits),
            notes=spec.notes,
        )
        session.add(place)
        session.flush()
    else:
        place.lat = spec.lat
        place.lng = spec.lng
        place.archived = False
        place.category = spec.category
        place.tags_json = list(spec.tags)
        place.traits_json = list(spec.traits)
        place.notes = spec.notes

    if place.visit_profile is None:
        session.add(
            PlaceVisitProfile(
                place_id=place.id,
                stay_min_minutes=spec.stay_min,
                stay_preferred_minutes=spec.stay_preferred,
                stay_max_minutes=spec.stay_max,
                price_band=spec.price_band,
                rating=spec.rating,
                accessibility_notes=None,
            )
        )
    else:
        place.visit_profile.stay_min_minutes = spec.stay_min
        place.visit_profile.stay_preferred_minutes = spec.stay_preferred
        place.visit_profile.stay_max_minutes = spec.stay_max
        place.visit_profile.price_band = spec.price_band
        place.visit_profile.rating = spec.rating

    session.query(PlaceAvailabilityRule).filter(
        PlaceAvailabilityRule.place_id == place.id
    ).delete()
    session.add(
        PlaceAvailabilityRule(
            place_id=place.id,
            weekday=None,
            open_minute=spec.open_min,
            close_minute=spec.close_min,
            valid_from=None,
            valid_to=None,
            last_admission_minute=None,
            closed_flag=False,
        )
    )
    session.add(
        PlaceSourceRecord(
            place_id=place.id,
            provider="seed",
            provider_place_id=spec.name.lower().replace(" ", "_"),
            source_url=None,
            fetched_at=datetime.now(timezone.utc),
            raw_payload=None,
            parser_version="seed_v1",
        )
    )


def run_seed(session: Session) -> None:
    for spec in SAMPLE_PLACES:
        _upsert_place(session, spec)
    session.commit()


def main() -> None:
    session = SessionLocal()
    try:
        run_seed(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
