from __future__ import annotations

from app.db.database import SessionLocal, reset_db
from app.db.seed import (
    SEED_DEPENDENCIES,
    SEED_POI_BY_KEY,
    h2m,
    resolve_seed_poi_ids,
    run_seed,
)
from app.models.poi import PoiDependencyRule, PoiMaster, PoiOpeningRule, PoiTag, PoiTagLink
from tests.helpers import add_custom_poi, setup_seeded_db


def _tag_slugs_for_poi(db, poi_id: int) -> set[str]:
    return {
        slug
        for (slug,) in (
            db.query(PoiTag.slug)
            .join(PoiTagLink, PoiTagLink.tag_id == PoiTag.id)
            .filter(PoiTagLink.poi_id == poi_id)
            .all()
        )
    }


def test_run_seed_does_not_overwrite_imported_poi_when_legacy_id_is_taken() -> None:
    reset_db()
    db = SessionLocal()
    try:
        imported = PoiMaster(
            id=1,
            name="Imported place",
            lat=35.5,
            lng=139.5,
            google_place_id="places/imported-place",
            primary_category="hub",
            is_active=True,
        )
        db.add(imported)
        db.commit()

        run_seed(db)
        db.refresh(imported)

        canonical_id = resolve_seed_poi_ids(db, ["nokogiri_nihonji_hell_peek"])[0]
        canonical = db.get(PoiMaster, canonical_id)
        assert canonical is not None

        assert imported.id == 1
        assert imported.seed_key is None
        assert imported.name == "Imported place"
        assert imported.google_place_id == "places/imported-place"
        assert canonical.id != imported.id
        assert canonical.seed_key == "nokogiri_nihonji_hell_peek"
        assert canonical.name == SEED_POI_BY_KEY["nokogiri_nihonji_hell_peek"].name
    finally:
        db.close()


def test_run_seed_preserves_imported_tags_and_dependencies_on_reseed() -> None:
    db = setup_seeded_db()
    try:
        imported = add_custom_poi(db, name="Imported cafe", tags=["cafe"])
        canonical_dependency_target = resolve_seed_poi_ids(db, ["kimura_peanuts"])[0]
        db.add(
            PoiDependencyRule(
                if_visit_poi_id=imported.id,
                require_poi_id=canonical_dependency_target,
                description="Imported POI custom dependency",
            )
        )
        db.commit()

        run_seed(db)

        assert _tag_slugs_for_poi(db, imported.id) == {"cafe"}
        preserved_dependency = (
            db.query(PoiDependencyRule)
            .filter(
                PoiDependencyRule.if_visit_poi_id == imported.id,
                PoiDependencyRule.require_poi_id == canonical_dependency_target,
            )
            .one_or_none()
        )
        assert preserved_dependency is not None
        assert preserved_dependency.description == "Imported POI custom dependency"
    finally:
        db.close()


def test_run_seed_resyncs_canonical_poi_fields_and_managed_dependencies() -> None:
    db = setup_seeded_db()
    try:
        poi_id = resolve_seed_poi_ids(db, ["satomi_no_yu"])[0]
        poi = db.get(PoiMaster, poi_id)
        assert poi is not None
        spec = SEED_POI_BY_KEY["satomi_no_yu"]

        poi.name = "Locally edited onsen"
        poi.google_place_id = "places/local-edit"
        poi.lat = 0.0
        poi.lng = 0.0
        poi.planning_profile.utility_default = 999
        poi.planning_profile.price_band = None
        db.query(PoiOpeningRule).filter(PoiOpeningRule.poi_id == poi.id).delete()
        db.add(
            PoiOpeningRule(
                poi_id=poi.id,
                weekday=None,
                open_minute=1,
                close_minute=2,
                valid_from=None,
                valid_to=None,
                holiday_note="mutated",
                last_admission_minute=None,
            )
        )
        db.query(PoiTagLink).filter(PoiTagLink.poi_id == poi.id).delete()
        cafe_tag = db.query(PoiTag).filter(PoiTag.slug == "cafe").one()
        db.add(PoiTagLink(poi_id=poi.id, tag_id=cafe_tag.id))

        extra_dependency_target = resolve_seed_poi_ids(db, ["kimura_peanuts"])[0]
        db.add(
            PoiDependencyRule(
                if_visit_poi_id=poi.id,
                require_poi_id=extra_dependency_target,
                description="local canonical dependency",
            )
        )
        db.commit()

        run_seed(db)
        db.refresh(poi)
        db.refresh(poi.planning_profile)

        assert poi.name == spec.name
        assert poi.google_place_id is None
        assert poi.lat == spec.lat
        assert poi.lng == spec.lng
        assert poi.planning_profile.utility_default == spec.utility_default
        assert poi.planning_profile.price_band == spec.price_band
        assert _tag_slugs_for_poi(db, poi.id) == set(spec.canonical_tags)

        opening_rules = (
            db.query(PoiOpeningRule)
            .filter(PoiOpeningRule.poi_id == poi.id)
            .all()
        )
        assert len(opening_rules) == 1
        assert opening_rules[0].open_minute == h2m(spec.tw_start_h) % (24 * 60)
        assert opening_rules[0].close_minute == h2m(min(spec.tw_end_h, 26.0))

        removed_dependency = (
            db.query(PoiDependencyRule)
            .filter(
                PoiDependencyRule.if_visit_poi_id == poi.id,
                PoiDependencyRule.require_poi_id == extra_dependency_target,
            )
            .one_or_none()
        )
        assert removed_dependency is None

        default_dependency = SEED_DEPENDENCIES[0]
        default_if_id = resolve_seed_poi_ids(db, [default_dependency.if_visit_seed_key])[0]
        default_require_id = resolve_seed_poi_ids(db, [default_dependency.require_seed_key])[0]
        preserved_default_dependency = (
            db.query(PoiDependencyRule)
            .filter(
                PoiDependencyRule.if_visit_poi_id == default_if_id,
                PoiDependencyRule.require_poi_id == default_require_id,
            )
            .one_or_none()
        )
        assert preserved_default_dependency is not None
        assert preserved_default_dependency.description == default_dependency.description
    finally:
        db.close()
