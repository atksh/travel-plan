"""Seed canonical POI data from docs/tmp_plan_problem.md (YAML section)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.poi import (
    PoiDependencyRule,
    PoiMaster,
    PoiOpeningRule,
    PoiPlanningProfile,
    PoiTag,
    PoiTagLink,
)
from app.models.source import PoiSourceSnapshot


def h2m(h: float) -> int:
    """Convert hour-of-day float (e.g. 8.5 for 08:30) to minutes from midnight."""
    return int(round(h * 60))


@dataclass(frozen=True)
class SeedPoiSpec:
    seed_key: str
    legacy_id: int
    name: str
    lat: float
    lng: float
    primary_category: str
    tw_start_h: float
    tw_end_h: float
    stay_min_h: float
    stay_max_h: float
    meal_start_h: float | None
    meal_end_h: float | None
    utility_default: int
    is_indoor: bool
    note: str | None
    canonical_tags: tuple[str, ...] = ()
    price_band: str | None = None


@dataclass(frozen=True)
class SeedDependencySpec:
    if_visit_seed_key: str
    require_seed_key: str
    description: str | None = None


def S(
    seed_key: str,
    legacy_id: int,
    name: str,
    lat: float,
    lng: float,
    primary_category: str,
    tw_start_h: float,
    tw_end_h: float,
    stay_min_h: float,
    stay_max_h: float,
    utility_default: int,
    *,
    meal: tuple[float | None, float | None] = (None, None),
    indoor: bool,
    note: str | None = None,
    tags: tuple[str, ...] = (),
    price: str | None = None,
) -> SeedPoiSpec:
    return SeedPoiSpec(
        seed_key=seed_key,
        legacy_id=legacy_id,
        name=name,
        lat=lat,
        lng=lng,
        primary_category=primary_category,
        tw_start_h=tw_start_h,
        tw_end_h=tw_end_h,
        stay_min_h=stay_min_h,
        stay_max_h=stay_max_h,
        meal_start_h=meal[0],
        meal_end_h=meal[1],
        utility_default=utility_default,
        is_indoor=indoor,
        note=note,
        canonical_tags=tags,
        price_band=price,
    )


def D(
    if_visit_seed_key: str,
    require_seed_key: str,
    description: str | None = None,
) -> SeedDependencySpec:
    return SeedDependencySpec(if_visit_seed_key, require_seed_key, description)


SEED_POIS: tuple[SeedPoiSpec, ...] = (
    S(
        "start_tokyo_iriya",
        0,
        "Tokyo Iriya (departure)",
        35.7274,
        139.791,
        "start",
        8.0,
        9.0,
        0.0,
        0.0,
        0,
        indoor=True,
        tags=("rain_safe",),
    ),
    S(
        "nokogiri_nihonji_hell_peek",
        1,
        "Nokogiri Nihonji Hell Peek",
        35.1562,
        139.8347,
        "sightseeing_active",
        9.0,
        15.0,
        1.5,
        2.5,
        18,
        indoor=False,
        note="Last admission 15:00",
        tags=("walk_heavy",),
    ),
    S(
        "ubara_risokyo",
        2,
        "Ubara Risokyo",
        35.1525,
        140.3208,
        "sightseeing_active",
        0.0,
        24.0,
        1.0,
        1.5,
        12,
        indoor=False,
        note="Small parking",
    ),
    S(
        "oyama_senmaida",
        3,
        "Oyama Senmaida",
        35.1235,
        140.104,
        "sightseeing_relax",
        9.0,
        16.0,
        0.5,
        1.0,
        10,
        indoor=False,
    ),
    S(
        "nojimasaki_lighthouse",
        4,
        "Nojimasaki Lighthouse",
        34.9175,
        139.867,
        "sightseeing_relax",
        9.0,
        16.5,
        0.5,
        1.0,
        11,
        indoor=False,
    ),
    S(
        "haraoka_pier_okamoto",
        5,
        "Haraoka Pier (Okamoto)",
        34.9976,
        139.876,
        "sunset",
        16.8,
        17.8,
        0.5,
        1.0,
        16,
        indoor=False,
        note="Walk from Biwa Club",
        tags=("sunset",),
    ),
    S(
        "tateyama_sunset_pier",
        6,
        "Tateyama Sunset Pier",
        34.9896,
        139.854,
        "sunset",
        16.8,
        17.8,
        0.5,
        1.0,
        15,
        indoor=False,
        tags=("sunset",),
    ),
    S(
        "satomi_no_yu",
        7,
        "Minamiboso Shiroyama Onsen Satomi no Yu",
        34.9985,
        139.868,
        "healing",
        10.0,
        22.5,
        1.5,
        3.0,
        17,
        indoor=True,
        note="Last entry 22:30",
        tags=("rain_safe",),
        price="premium",
    ),
    S(
        "zekuu",
        8,
        "Boso Kamogawa Onsen ZEKUU",
        35.1068,
        140.105,
        "healing",
        11.0,
        21.0,
        1.0,
        2.0,
        14,
        indoor=True,
        tags=("rain_safe",),
        price="premium",
    ),
    S(
        "ryoshi_ryori_kanaya",
        9,
        "Ryoshi Ryori Kanaya",
        35.1772,
        139.8349,
        "lunch",
        10.0,
        18.0,
        1.0,
        1.5,
        14,
        meal=(11.0, 14.0),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="moderate",
    ),
    S(
        "the_fish_bayside_kanaya",
        10,
        "The Fish BAYSIDE KANAYA",
        35.1772,
        139.8349,
        "lunch",
        11.0,
        19.0,
        1.0,
        1.5,
        15,
        meal=(11.0, 14.0),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="moderate",
    ),
    S(
        "hamano_osakana_club",
        11,
        "Hamano Daidokoro Osakana Club",
        34.9978,
        139.876,
        "lunch",
        11.0,
        15.0,
        1.0,
        1.5,
        13,
        meal=(11.0, 13.5),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="casual",
    ),
    S(
        "banya_honkan",
        12,
        "Banya Honkan",
        35.1415,
        139.839,
        "lunch",
        9.5,
        17.75,
        1.0,
        1.5,
        14,
        meal=(11.0, 14.0),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="casual",
    ),
    S(
        "kamogawa_seaside_base",
        13,
        "Kamogawa SEASIDE BASE",
        35.1145,
        140.098,
        "lunch",
        9.0,
        21.0,
        1.0,
        1.5,
        12,
        meal=(11.0, 14.0),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="moderate",
    ),
    S(
        "yamato_sushi_tomiura",
        14,
        "Minamiboso Yamato Sushi Tomiura",
        34.9985,
        139.868,
        "dinner",
        11.0,
        21.0,
        1.0,
        1.5,
        14,
        meal=(17.5, 20.0),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="premium",
    ),
    S(
        "kaisen_shokudo_tomiuratei",
        15,
        "Kaisen Shokudo Tomiuratei",
        35.0,
        139.85,
        "dinner",
        10.0,
        20.0,
        1.0,
        1.5,
        13,
        meal=(17.5, 19.5),
        indoor=True,
        tags=("seafood", "rain_safe"),
        price="casual",
    ),
    S(
        "kimura_peanuts",
        16,
        "Kimura Peanuts",
        34.9965,
        139.862,
        "sweets",
        9.0,
        18.0,
        0.5,
        1.0,
        12,
        indoor=True,
        tags=("rain_safe", "cafe"),
        price="casual",
    ),
    S(
        "michi_no_eki_tomiura_biwakurabu",
        17,
        "Michi no Eki Tomiura Biwakurabu",
        34.9976,
        139.876,
        "sweets",
        10.0,
        17.0,
        0.5,
        1.0,
        13,
        indoor=True,
        note="Cafe LO weekdays",
        tags=("rain_safe", "cafe"),
        price="casual",
    ),
    S(
        "nagisa_no_eki_tateyama",
        18,
        "Nagisa no Eki Tateyama",
        34.9896,
        139.854,
        "hub",
        9.0,
        16.75,
        1.0,
        2.0,
        10,
        indoor=True,
        note="Rain hub",
        tags=("rain_safe",),
    ),
    S(
        "michi_no_eki_hota_shogakko",
        19,
        "Michi no Eki Hota Shogakko",
        35.1415,
        139.839,
        "hub",
        9.0,
        17.0,
        1.0,
        1.5,
        9,
        indoor=True,
        tags=("rain_safe",),
    ),
    S(
        "end_tokyo_iriya",
        99,
        "Tokyo Iriya (return)",
        35.7274,
        139.791,
        "end",
        21.0,
        25.0,
        0.0,
        0.0,
        0,
        indoor=True,
        tags=("rain_safe",),
    ),
)

SEED_POI_BY_KEY: dict[str, SeedPoiSpec] = {spec.seed_key: spec for spec in SEED_POIS}
SEED_KEY_BY_LEGACY_ID: dict[int, str] = {
    spec.legacy_id: spec.seed_key for spec in SEED_POIS
}
TRIP_CANDIDATE_SEED_KEYS: tuple[str, ...] = tuple(
    spec.seed_key
    for spec in SEED_POIS
    if spec.primary_category not in {"start", "end"}
)
DEFAULT_MUST_VISIT_SEED_KEYS: tuple[str, ...] = (
    "nokogiri_nihonji_hell_peek",
    "satomi_no_yu",
)

SEED_DEPENDENCIES: tuple[SeedDependencySpec, ...] = (
    D(
        "haraoka_pier_okamoto",
        "michi_no_eki_tomiura_biwakurabu",
        "Park at Biwa Club and walk to Haraoka Pier",
    ),
)

TAGS: tuple[tuple[str, str], ...] = (
    ("seafood", "Seafood"),
    ("sunset", "Sunset"),
    ("rain_safe", "Rain safe"),
    ("walk_heavy", "Walk heavy"),
    ("high_wait_risk", "High wait risk"),
    ("cafe", "Cafe"),
)


def resolve_seed_poi_ids(
    session: Session,
    seed_keys: Iterable[str],
    *,
    trip_selectable_only: bool = False,
) -> list[int]:
    ordered_seed_keys = tuple(dict.fromkeys(seed_keys))
    if not ordered_seed_keys:
        return []

    query = session.query(PoiMaster.seed_key, PoiMaster.id).filter(
        PoiMaster.seed_key.in_(ordered_seed_keys)
    )
    if trip_selectable_only:
        query = query.filter(PoiMaster.primary_category.notin_(("start", "end")))
    resolved_by_key = {
        seed_key: poi_id
        for seed_key, poi_id in query.all()
        if seed_key is not None
    }
    return [resolved_by_key[key] for key in ordered_seed_keys if key in resolved_by_key]


def seed_tags(session: Session) -> dict[str, PoiTag]:
    out: dict[str, PoiTag] = {}
    for slug, label in TAGS:
        existing = session.query(PoiTag).filter(PoiTag.slug == slug).one_or_none()
        if existing is None:
            existing = PoiTag(slug=slug, label=label)
            session.add(existing)
            session.flush()
        out[slug] = existing
    return out


def _assign_fields(obj: object, values: dict[str, object]) -> None:
    for field, value in values.items():
        setattr(obj, field, value)


def _seed_poi_fields(spec: SeedPoiSpec) -> dict[str, object]:
    return {
        "seed_key": spec.seed_key,
        "name": spec.name,
        "lat": spec.lat,
        "lng": spec.lng,
        "google_place_id": None,
        "primary_category": spec.primary_category,
        "is_active": True,
    }


def _profile_fields(spec: SeedPoiSpec) -> dict[str, object]:
    meal_start = h2m(spec.meal_start_h) if spec.meal_start_h is not None else None
    meal_end = h2m(spec.meal_end_h) if spec.meal_end_h is not None else None
    return {
        "stay_min_minutes": int(spec.stay_min_h * 60),
        "stay_max_minutes": int(spec.stay_max_h * 60),
        "meal_window_start_min": meal_start,
        "meal_window_end_min": meal_end,
        "is_indoor": spec.is_indoor,
        "sunset_score": 3 if spec.primary_category == "sunset" else 0,
        "scenic_score": 3 if "sightseeing" in spec.primary_category else 2,
        "relax_score": 3 if spec.primary_category == "healing" else 1,
        "price_band": spec.price_band,
        "parking_note": None,
        "difficulty_note": spec.note,
        "utility_default": spec.utility_default,
    }


def _create_seed_poi(session: Session, spec: SeedPoiSpec) -> PoiMaster:
    existing_legacy_row = session.get(PoiMaster, spec.legacy_id)
    poi = (
        PoiMaster(id=spec.legacy_id, **_seed_poi_fields(spec))
        if existing_legacy_row is None
        else PoiMaster(**_seed_poi_fields(spec))
    )
    session.add(poi)
    session.flush()
    return poi


def _sync_seed_poi_core(
    session: Session,
    spec: SeedPoiSpec,
) -> PoiMaster:
    poi = (
        session.query(PoiMaster)
        .filter(PoiMaster.seed_key == spec.seed_key)
        .one_or_none()
    )
    if poi is None:
        poi = _create_seed_poi(session, spec)
    _assign_fields(poi, _seed_poi_fields(spec))
    return poi


def _sync_seed_profile(session: Session, poi: PoiMaster, spec: SeedPoiSpec) -> None:
    profile = (
        session.query(PoiPlanningProfile)
        .filter(PoiPlanningProfile.poi_id == poi.id)
        .one_or_none()
    )
    values = _profile_fields(spec)
    if profile is None:
        session.add(PoiPlanningProfile(poi_id=poi.id, **values))
        return
    _assign_fields(profile, values)


def _sync_seed_opening_rule(session: Session, poi: PoiMaster, spec: SeedPoiSpec) -> None:
    session.query(PoiOpeningRule).filter(PoiOpeningRule.poi_id == poi.id).delete()
    open_minute = h2m(spec.tw_start_h) % (24 * 60)
    close_minute = h2m(min(spec.tw_end_h, 26.0))
    last_admission_minute = h2m(15.0) if spec.seed_key == "nokogiri_nihonji_hell_peek" else None
    session.add(
        PoiOpeningRule(
            poi_id=poi.id,
            weekday=None,
            open_minute=open_minute,
            close_minute=close_minute,
            valid_from=None,
            valid_to=None,
            holiday_note=None,
            last_admission_minute=last_admission_minute,
        )
    )


def _sync_seed_snapshot(session: Session, poi: PoiMaster, now: datetime) -> None:
    session.query(PoiSourceSnapshot).filter(
        PoiSourceSnapshot.poi_id == poi.id,
        PoiSourceSnapshot.source_type == "seed",
    ).delete()
    session.add(
        PoiSourceSnapshot(
            poi_id=poi.id,
            source_type="seed",
            source_url=None,
            fetched_at=now,
            raw_payload=None,
            parser_version="seed_v1",
            confidence=0.5,
        )
    )


def _sync_seed_tags(
    session: Session,
    poi: PoiMaster,
    spec: SeedPoiSpec,
    tags: dict[str, PoiTag],
) -> None:
    session.query(PoiTagLink).filter(PoiTagLink.poi_id == poi.id).delete()
    for slug in spec.canonical_tags:
        session.add(PoiTagLink(poi_id=poi.id, tag_id=tags[slug].id))


def _sync_seed_dependencies(
    session: Session,
    seed_pois_by_key: dict[str, PoiMaster],
) -> None:
    canonical_poi_ids = {poi.id for poi in seed_pois_by_key.values()}
    if not canonical_poi_ids:
        return

    desired_by_pair: dict[tuple[int, int], str | None] = {}
    for spec in SEED_DEPENDENCIES:
        if_visit_poi = seed_pois_by_key[spec.if_visit_seed_key]
        require_poi = seed_pois_by_key[spec.require_seed_key]
        desired_by_pair[(if_visit_poi.id, require_poi.id)] = spec.description

    existing = (
        session.query(PoiDependencyRule)
        .filter(
            PoiDependencyRule.if_visit_poi_id.in_(canonical_poi_ids),
            PoiDependencyRule.require_poi_id.in_(canonical_poi_ids),
        )
        .all()
    )
    existing_by_pair = {
        (rule.if_visit_poi_id, rule.require_poi_id): rule for rule in existing
    }

    for pair, rule in existing_by_pair.items():
        if pair not in desired_by_pair:
            session.delete(rule)

    for pair, description in desired_by_pair.items():
        existing_rule = existing_by_pair.get(pair)
        if existing_rule is None:
            session.add(
                PoiDependencyRule(
                    if_visit_poi_id=pair[0],
                    require_poi_id=pair[1],
                    description=description,
                )
            )
        else:
            existing_rule.description = description


def seed_pois(session: Session) -> None:
    tags = seed_tags(session)
    now = datetime.now(timezone.utc)
    seed_pois_by_key: dict[str, PoiMaster] = {}

    for spec in SEED_POIS:
        poi = _sync_seed_poi_core(session, spec)
        _sync_seed_profile(session, poi, spec)
        _sync_seed_opening_rule(session, poi, spec)
        _sync_seed_snapshot(session, poi, now)
        _sync_seed_tags(session, poi, spec, tags)
        seed_pois_by_key[spec.seed_key] = poi

    _sync_seed_dependencies(session, seed_pois_by_key)
    session.commit()


def run_seed(session: Session) -> None:
    seed_pois(session)


def main() -> None:
    session = SessionLocal()
    try:
        run_seed(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
