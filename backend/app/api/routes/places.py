from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.errors import RequestContractError
from app.models.place import Place, PlaceAvailabilityRule, PlaceSourceRecord, PlaceVisitProfile
from app.schemas.common import OkResponse
from app.schemas.place import (
    PlaceCreateIn,
    PlaceDetailOut,
    PlaceImportIn,
    PlaceListOut,
    PlacePatchIn,
    PlaceSearchAreaIn,
    PlaceSearchResponseOut,
    PlaceSearchTextIn,
)
from app.services.google_places import get_place_details, search_places_area, search_places_text
from app.services.workspace import serialize_place_detail, serialize_place_summary

router = APIRouter(prefix="/places", tags=["places"])


def _get_place_or_404(session: Session, place_id: int) -> Place:
    place = session.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


def _price_band_from_provider(price_level: str | None) -> str | None:
    if price_level == "PRICE_LEVEL_INEXPENSIVE":
        return "casual"
    if price_level == "PRICE_LEVEL_MODERATE":
        return "moderate"
    if price_level in {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}:
        return "premium"
    return None


def _normalize_place_category(primary_type: str | None) -> str | None:
    if primary_type is None:
        return None
    normalized = primary_type.lower()
    if "cafe" in normalized:
        return "cafe"
    if "museum" in normalized or "gallery" in normalized:
        return "museum"
    if "park" in normalized or "beach" in normalized or "trail" in normalized:
        return "nature"
    if "restaurant" in normalized or "food" in normalized or "meal" in normalized:
        return "restaurant"
    if "spa" in normalized or "onsen" in normalized:
        return "onsen"
    return normalized


def _traits_from_provider(primary_type: str | None) -> list[str]:
    if primary_type is None:
        return []
    lowered = primary_type.lower()
    traits: list[str] = []
    if any(token in lowered for token in ("museum", "gallery", "restaurant", "cafe", "spa", "onsen")):
        traits.append("indoor")
    if any(token in lowered for token in ("park", "beach", "trail", "pier")):
        traits.append("outdoor")
    return traits


def _create_or_update_visit_profile(place: Place, visit_profile: dict | None) -> None:
    visit_profile = visit_profile or {}
    min_minutes = int(visit_profile.get("stay_min_minutes", 30))
    preferred_minutes = int(visit_profile.get("stay_preferred_minutes", max(min_minutes, 45)))
    max_minutes = int(visit_profile.get("stay_max_minutes", max(preferred_minutes, 90)))
    if place.visit_profile is None:
        place.visit_profile = PlaceVisitProfile(
            stay_min_minutes=min_minutes,
            stay_preferred_minutes=preferred_minutes,
            stay_max_minutes=max_minutes,
            price_band=visit_profile.get("price_band"),
            rating=visit_profile.get("rating"),
            accessibility_notes=visit_profile.get("accessibility_notes"),
        )
    else:
        place.visit_profile.stay_min_minutes = min_minutes
        place.visit_profile.stay_preferred_minutes = preferred_minutes
        place.visit_profile.stay_max_minutes = max_minutes
        place.visit_profile.price_band = visit_profile.get("price_band")
        place.visit_profile.rating = visit_profile.get("rating")
        place.visit_profile.accessibility_notes = visit_profile.get("accessibility_notes")


def _replace_availability_rules(place: Place, availability_rules: list[dict]) -> None:
    place.availability_rules.clear()
    if not availability_rules:
        place.availability_rules.append(
            PlaceAvailabilityRule(
                weekday=None,
                open_minute=0,
                close_minute=24 * 60,
                valid_from=None,
                valid_to=None,
                last_admission_minute=None,
                closed_flag=False,
            )
        )
        return
    for rule in availability_rules:
        place.availability_rules.append(
            PlaceAvailabilityRule(
                weekday=rule.get("weekday"),
                open_minute=rule["open_minute"],
                close_minute=rule["close_minute"],
                valid_from=rule.get("valid_from"),
                valid_to=rule.get("valid_to"),
                last_admission_minute=rule.get("last_admission_minute"),
                closed_flag=bool(rule.get("closed_flag", False)),
            )
        )


@router.get("", response_model=PlaceListOut)
def list_places(
    q: str | None = Query(default=None),
    source: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    tags: list[str] = Query(default=[]),
    traits: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
) -> PlaceListOut:
    query = db.query(Place).order_by(Place.id.asc())
    if q:
        query = query.filter(Place.name.ilike(f"%{q}%"))
    if source:
        query = query.filter(Place.source == source)
    if archived is not None:
        query = query.filter(Place.archived.is_(archived))
    places = query.all()
    filtered = [
        place
        for place in places
        if set(tags).issubset(set(place.tags_json or []))
        and set(traits).issubset(set(place.traits_json or []))
    ]
    return PlaceListOut(items=[serialize_place_summary(place) for place in filtered], next_cursor=None)


@router.post("/search-text", response_model=PlaceSearchResponseOut)
async def search_places_text_endpoint(body: PlaceSearchTextIn) -> PlaceSearchResponseOut:
    return PlaceSearchResponseOut(results=await search_places_text(body.query, body.region))


@router.post("/search-area", response_model=PlaceSearchResponseOut)
async def search_places_area_endpoint(body: PlaceSearchAreaIn) -> PlaceSearchResponseOut:
    if body.center is None and body.bounds is None:
        raise RequestContractError(
            "RULE_VALIDATION_FAILED",
            "search-area requires either center+radius or bounds.",
            details={"field": "center"},
        )
    if body.center is not None:
        center_lat = body.center["lat"]
        center_lng = body.center["lng"]
        radius_m = body.radius_m or 5000
    else:
        center_lat = (body.bounds.north + body.bounds.south) / 2
        center_lng = (body.bounds.east + body.bounds.west) / 2
        radius_m = body.radius_m or 5000
    results = await search_places_area(
        center_lat=center_lat,
        center_lng=center_lng,
        radius_m=radius_m,
        included_types=body.included_types,
    )
    return PlaceSearchResponseOut(results=results)


@router.post("/import", response_model=PlaceDetailOut, status_code=201)
async def import_place(body: PlaceImportIn, db: Session = Depends(get_db)) -> PlaceDetailOut:
    if body.provider != "google_places":
        raise RequestContractError(
            "PLACE_IMPORT_UNSUPPORTED",
            f"Unsupported provider={body.provider}.",
            status_code=422,
        )
    provider_detail = await get_place_details(body.provider_place_id)
    existing_source = (
        db.query(PlaceSourceRecord)
        .filter(
            PlaceSourceRecord.provider == body.provider,
            PlaceSourceRecord.provider_place_id == provider_detail["provider_place_id"],
        )
        .order_by(PlaceSourceRecord.id.desc())
        .first()
    )
    place = None if existing_source is None else existing_source.place
    overrides = body.overrides or {}
    if place is None:
        place = Place(
            name=overrides.get("name", provider_detail["name"]),
            lat=float(provider_detail["lat"]),
            lng=float(provider_detail["lng"]),
            source=body.provider,
            archived=False,
            category=overrides.get("category", _normalize_place_category(provider_detail.get("primary_type"))),
            tags_json=list(overrides.get("tags", [])),
            traits_json=list(overrides.get("traits", _traits_from_provider(provider_detail.get("primary_type")))),
            notes=overrides.get("notes"),
        )
        db.add(place)
        db.flush()
    else:
        place.name = overrides.get("name", provider_detail["name"])
        place.lat = float(provider_detail["lat"])
        place.lng = float(provider_detail["lng"])
        place.archived = False
        place.category = overrides.get("category", _normalize_place_category(provider_detail.get("primary_type")))
        place.tags_json = list(overrides.get("tags", place.tags_json or []))
        place.traits_json = list(overrides.get("traits", _traits_from_provider(provider_detail.get("primary_type"))))
        place.notes = overrides.get("notes", place.notes)
    _create_or_update_visit_profile(
        place,
        {
            "stay_min_minutes": 30,
            "stay_preferred_minutes": 45,
            "stay_max_minutes": 90,
            "price_band": _price_band_from_provider(provider_detail.get("price_level")),
            "rating": provider_detail.get("rating"),
        },
    )
    opening_rules = []
    for period in (provider_detail.get("opening_hours") or {}).get("periods", []):
        open_info = period.get("open") or {}
        close_info = period.get("close") or {}
        if "day" not in open_info:
            continue
        opening_rules.append(
            {
                "weekday": (int(open_info["day"]) - 1) % 7,
                "open_minute": int(open_info.get("hour", 0)) * 60 + int(open_info.get("minute", 0)),
                "close_minute": int(close_info.get("hour", 24)) * 60 + int(close_info.get("minute", 0)),
                "closed_flag": False,
            }
        )
    _replace_availability_rules(place, opening_rules)
    db.add(
        PlaceSourceRecord(
            place_id=place.id,
            provider=body.provider,
            provider_place_id=provider_detail["provider_place_id"],
            source_url=provider_detail.get("website_uri"),
            fetched_at=datetime.now(timezone.utc),
            raw_payload=str(provider_detail.get("raw_payload")),
            parser_version="google_places_v1",
        )
    )
    db.commit()
    db.refresh(place)
    return PlaceDetailOut.model_validate(serialize_place_detail(place))


@router.post("", response_model=PlaceDetailOut, status_code=201)
def create_place(body: PlaceCreateIn, db: Session = Depends(get_db)) -> PlaceDetailOut:
    place = Place(
        name=body.name,
        lat=body.lat,
        lng=body.lng,
        source="manual",
        archived=False,
        category=body.category,
        tags_json=list(body.tags),
        traits_json=list(body.traits),
        notes=body.note,
    )
    db.add(place)
    db.flush()
    _create_or_update_visit_profile(place, body.visit_profile)
    _replace_availability_rules(place, body.availability_rules)
    db.commit()
    db.refresh(place)
    return PlaceDetailOut.model_validate(serialize_place_detail(place))


@router.get("/{place_id}", response_model=PlaceDetailOut)
def get_place(place_id: int, db: Session = Depends(get_db)) -> PlaceDetailOut:
    return PlaceDetailOut.model_validate(serialize_place_detail(_get_place_or_404(db, place_id)))


@router.patch("/{place_id}", response_model=PlaceDetailOut)
def patch_place(place_id: int, body: PlacePatchIn, db: Session = Depends(get_db)) -> PlaceDetailOut:
    place = _get_place_or_404(db, place_id)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates:
        place.name = updates["name"]
    if "category" in updates:
        place.category = updates["category"]
    if "tags" in updates:
        place.tags_json = list(updates["tags"] or [])
    if "traits" in updates:
        place.traits_json = list(updates["traits"] or [])
    if "notes" in updates:
        place.notes = updates["notes"]
    if "archived" in updates:
        place.archived = updates["archived"]
    if "visit_profile" in updates:
        _create_or_update_visit_profile(place, updates["visit_profile"])
    if "availability_rules" in updates:
        _replace_availability_rules(place, updates["availability_rules"] or [])
    db.commit()
    db.refresh(place)
    return PlaceDetailOut.model_validate(serialize_place_detail(place))


@router.delete("/{place_id}", response_model=OkResponse)
def delete_place(place_id: int, db: Session = Depends(get_db)) -> OkResponse:
    place = _get_place_or_404(db, place_id)
    if place.trip_candidates:
        place.archived = True
    else:
        db.delete(place)
    db.commit()
    return OkResponse(ok=True)
