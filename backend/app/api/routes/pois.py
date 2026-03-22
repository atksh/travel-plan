import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.errors import RequestContractError
from app.models.poi import (
    PoiMaster,
    PoiOpeningRule,
    PoiPlanningProfile,
    PoiTag,
    PoiTagLink,
)
from app.models.source import PoiSourceSnapshot
from app.schemas.poi import (
    PoiDetailOut,
    PoiImportBody,
    PoiOut,
    PoiPatch,
    PoiSearchBody,
    PoiSearchResponseOut,
)
from app.services.google_places import get_place_details, search_places_text

router = APIRouter(prefix="/pois", tags=["pois"])
INTERNAL_TRIP_POI_CATEGORIES = frozenset({"start", "end"})


def _serialize_poi_detail(poi: PoiMaster) -> PoiDetailOut:
    return PoiDetailOut(
        id=poi.id,
        name=poi.name,
        lat=poi.lat,
        lng=poi.lng,
        google_place_id=poi.google_place_id,
        primary_category=poi.primary_category,
        is_active=poi.is_active,
        planning_profile=poi.planning_profile,
        opening_rules=sorted(
            poi.opening_rules,
            key=lambda rule: (rule.weekday is None, rule.weekday or -1, rule.open_minute),
        ),
        tags=sorted({link.tag.slug for link in poi.tag_links}),
    )


def _google_day_to_weekday(day: int) -> int:
    return 6 if day == 0 else day - 1


def _is_generic_dining_type(primary_type: str | None) -> bool:
    if not primary_type:
        return False
    lowered = primary_type.lower()
    return (
        "restaurant" in lowered
        or "food" in lowered
        or "meal" in lowered
    )


def _infer_category(
    primary_type: str | None,
    *,
    category_override: str | None = None,
) -> str:
    if category_override is not None:
        return category_override
    if not primary_type:
        raise RequestContractError(
            "PLACE_PRIMARY_TYPE_MISSING",
            "Google Place primaryType is required for import.",
        )
    lowered = primary_type.lower()
    if "cafe" in lowered or "bakery" in lowered:
        return "sweets"
    if "spa" in lowered or "onsen" in lowered or "hot_spring" in lowered:
        return "healing"
    if "pier" in lowered:
        return "sunset"
    if _is_generic_dining_type(primary_type):
        return "lunch"
    if "museum" in lowered or "gallery" in lowered or "aquarium" in lowered:
        return "hub"
    if any(keyword in lowered for keyword in ("park", "pier", "beach", "trail", "lighthouse")):
        return "sightseeing_relax"
    raise RequestContractError(
        "PLACE_PRIMARY_TYPE_UNSUPPORTED",
        "Google Place primaryType is not supported for import.",
        details={"primary_type": primary_type},
    )


def _infer_stay_bounds(category: str) -> tuple[int, int]:
    if category in {"lunch", "dinner"}:
        return 60, 90
    if category == "healing":
        return 90, 180
    if category == "sweets":
        return 30, 60
    if category == "hub":
        return 45, 90
    return 45, 90


def _infer_meal_window(category: str) -> tuple[int | None, int | None]:
    if category == "lunch":
        return 11 * 60, 14 * 60
    if category == "dinner":
        return 17 * 60 + 30, 20 * 60
    return None, None


def _infer_indoor(primary_type: str | None) -> bool:
    if not primary_type:
        raise RequestContractError(
            "PLACE_PRIMARY_TYPE_MISSING",
            "Google Place primaryType is required to infer indoor/outdoor classification.",
        )
    lowered = primary_type.lower()
    outdoor_keywords = {"park", "pier", "beach", "trail", "campground"}
    return not any(keyword in lowered for keyword in outdoor_keywords)


def _has_cafe_primary_type(primary_type: str | None) -> bool:
    if not primary_type:
        return False
    lowered = primary_type.lower()
    return "cafe" in lowered or "bakery" in lowered


def _map_price_level(price_level: str | None) -> str | None:
    if price_level == "PRICE_LEVEL_INEXPENSIVE":
        return "casual"
    if price_level == "PRICE_LEVEL_MODERATE":
        return "moderate"
    if price_level in {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}:
        return "premium"
    return None


def _infer_utility(place: dict) -> int:
    if not isinstance(place.get("rating"), (int, float)):
        raise RequestContractError(
            "PLACE_RATING_MISSING",
            "Google Place rating is required for import.",
        )
    if not isinstance(place.get("userRatingCount"), int):
        raise RequestContractError(
            "PLACE_RATING_COUNT_MISSING",
            "Google Place userRatingCount is required for import.",
        )
    rating = float(place["rating"])
    user_rating_count = int(place["userRatingCount"])
    if rating <= 0:
        raise RequestContractError(
            "PLACE_RATING_INVALID",
            "Google Place rating must be greater than zero.",
            details={"rating": rating},
        )
    social_boost = min(user_rating_count // 200, 4)
    return max(8, int(round(rating * 3)) + social_boost)


def _get_or_create_tag(db: Session, slug: str, label: str) -> PoiTag:
    tag = db.query(PoiTag).filter(PoiTag.slug == slug).one_or_none()
    if tag is None:
        tag = PoiTag(slug=slug, label=label)
        db.add(tag)
        db.flush()
    return tag


def _sync_import_tags(
    db: Session,
    poi: PoiMaster,
    *,
    has_cafe_tag: bool,
) -> None:
    cafe_tag = _get_or_create_tag(db, "cafe", "Cafe")
    existing_link = (
        db.query(PoiTagLink)
        .filter(PoiTagLink.poi_id == poi.id, PoiTagLink.tag_id == cafe_tag.id)
        .one_or_none()
    )
    if has_cafe_tag:
        if existing_link is None:
            db.add(PoiTagLink(poi_id=poi.id, tag_id=cafe_tag.id))
        return
    if existing_link is not None:
        db.delete(existing_link)


def _sync_opening_rules(db: Session, poi: PoiMaster, place: dict) -> None:
    db.query(PoiOpeningRule).filter(PoiOpeningRule.poi_id == poi.id).delete()
    opening_hours = place.get("regularOpeningHours") or {}
    periods = opening_hours.get("periods") or []
    if not periods:
        raise RequestContractError(
            "PLACE_OPENING_HOURS_MISSING",
            "Google Place regularOpeningHours.periods is required for import.",
        )
    for period in periods:
        open_info = period.get("open") or {}
        close_info = period.get("close") or {}
        if "day" not in open_info:
            continue
        open_day = int(open_info.get("day", 0))
        open_hour = int(open_info.get("hour", 0))
        open_minute = int(open_info.get("minute", 0))
        close_day = int(close_info.get("day", open_day))
        close_hour = int(close_info.get("hour", 24))
        close_minute = int(close_info.get("minute", 0))
        weekday = _google_day_to_weekday(open_day)
        open_total = open_hour * 60 + open_minute
        close_total = close_hour * 60 + close_minute
        day_delta = (close_day - open_day) % 7
        if day_delta > 0:
            close_total += day_delta * 24 * 60
        db.add(
            PoiOpeningRule(
                poi_id=poi.id,
                weekday=weekday,
                open_minute=open_total,
                close_minute=close_total,
                valid_from=None,
                valid_to=None,
                holiday_note=None,
                last_admission_minute=None,
            )
        )


@router.get("", response_model=list[PoiOut])
def list_pois(db: Session = Depends(get_db)) -> list[PoiMaster]:
    return (
        db.query(PoiMaster)
        .filter(PoiMaster.primary_category.notin_(tuple(INTERNAL_TRIP_POI_CATEGORIES)))
        .filter(PoiMaster.is_active.is_(True))
        .order_by(PoiMaster.id)
        .all()
    )


@router.get("/{poi_id}", response_model=PoiDetailOut)
def get_poi(poi_id: int, db: Session = Depends(get_db)) -> PoiDetailOut:
    poi = db.get(PoiMaster, poi_id)
    if poi is None:
        raise HTTPException(status_code=404, detail="POI not found")
    return _serialize_poi_detail(poi)


@router.patch("/{poi_id}", response_model=PoiDetailOut)
def patch_poi(
    poi_id: int, body: PoiPatch, db: Session = Depends(get_db)
) -> PoiDetailOut:
    poi = db.get(PoiMaster, poi_id)
    if poi is None:
        raise HTTPException(status_code=404, detail="POI not found")
    if body.name is not None:
        poi.name = body.name
    if body.is_active is not None:
        poi.is_active = body.is_active
    db.commit()
    db.refresh(poi)
    return _serialize_poi_detail(poi)


@router.post("/search", response_model=PoiSearchResponseOut)
async def search_pois(body: PoiSearchBody) -> dict:
    results = await search_places_text(body.query, body.region)
    return {"results": results}


@router.post("/import", response_model=PoiDetailOut)
async def import_poi(body: PoiImportBody, db: Session = Depends(get_db)) -> PoiDetailOut:
    place = await get_place_details(body.place_id)
    place_id = place.get("id") or body.place_id.removeprefix("places/")
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Place details missing location")

    display_name = body.display_name or (place.get("displayName") or {}).get("text")
    if not isinstance(display_name, str) or not display_name.strip():
        raise RequestContractError(
            "PLACE_DISPLAY_NAME_MISSING",
            "Google Place displayName.text is required for import.",
            details={"place_id": place_id},
        )
    primary_type = place.get("primaryType")
    if _is_generic_dining_type(primary_type) and body.category_override is None:
        raise HTTPException(
            status_code=400,
            detail="Dining places require category_override of lunch or dinner",
        )
    category = _infer_category(
        primary_type,
        category_override=body.category_override,
    )
    is_active = place.get("businessStatus") != "CLOSED_PERMANENTLY"
    price_band = _map_price_level(place.get("priceLevel"))

    poi = (
        db.query(PoiMaster)
        .filter(PoiMaster.google_place_id == place_id)
        .one_or_none()
    )
    if poi is None:
        poi = PoiMaster(
            name=display_name,
            lat=float(lat),
            lng=float(lng),
            google_place_id=place_id,
            primary_category=category,
            is_active=is_active,
        )
        db.add(poi)
        db.flush()
    else:
        poi.name = display_name
        poi.lat = float(lat)
        poi.lng = float(lng)
        poi.google_place_id = place_id
        poi.primary_category = category
        poi.is_active = is_active

    stay_min, stay_max = _infer_stay_bounds(category)
    meal_window_start_min, meal_window_end_min = _infer_meal_window(category)
    if poi.planning_profile is None:
        db.add(
            PoiPlanningProfile(
                poi_id=poi.id,
                stay_min_minutes=stay_min,
                stay_max_minutes=stay_max,
                meal_window_start_min=meal_window_start_min,
                meal_window_end_min=meal_window_end_min,
                is_indoor=_infer_indoor(primary_type),
                sunset_score=3 if category == "sunset" else 0,
                scenic_score=2 if category.startswith("sightseeing") else 1,
                relax_score=3 if category == "healing" else 1,
                price_band=price_band,
                parking_note=None,
                difficulty_note=f"Imported from Google Places primaryType={primary_type}",
                utility_default=_infer_utility(place),
            )
        )
    else:
        poi.planning_profile.stay_min_minutes = stay_min
        poi.planning_profile.stay_max_minutes = stay_max
        poi.planning_profile.is_indoor = _infer_indoor(primary_type)
        poi.planning_profile.utility_default = _infer_utility(place)
        poi.planning_profile.meal_window_start_min = meal_window_start_min
        poi.planning_profile.meal_window_end_min = meal_window_end_min
        poi.planning_profile.difficulty_note = (
            poi.planning_profile.difficulty_note
            or f"Imported from Google Places primaryType={primary_type}"
        )
        poi.planning_profile.price_band = price_band

    _sync_import_tags(db, poi, has_cafe_tag=_has_cafe_primary_type(primary_type))

    _sync_opening_rules(db, poi, place)
    db.add(
        PoiSourceSnapshot(
            poi_id=poi.id,
            source_type="google_places",
            source_url=f"https://places.googleapis.com/v1/places/{place_id}",
            fetched_at=datetime.now(timezone.utc),
            raw_payload=json.dumps(place, ensure_ascii=False),
            parser_version="place_details_v1",
            confidence=0.8,
        )
    )
    db.commit()
    db.refresh(poi)
    return _serialize_poi_detail(poi)
