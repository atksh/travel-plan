from typing import Literal

from pydantic import BaseModel, Field


class PoiPlanningProfileOut(BaseModel):
    stay_min_minutes: int
    stay_max_minutes: int
    meal_window_start_min: int | None
    meal_window_end_min: int | None
    is_indoor: bool
    sunset_score: int
    scenic_score: int
    relax_score: int
    price_band: str | None
    parking_note: str | None
    difficulty_note: str | None
    utility_default: int

    model_config = {"from_attributes": True}


class PoiOpeningRuleOut(BaseModel):
    weekday: int | None
    open_minute: int
    close_minute: int
    valid_from: str | None
    valid_to: str | None
    holiday_note: str | None
    last_admission_minute: int | None

    model_config = {"from_attributes": True}


class PoiOut(BaseModel):
    id: int
    name: str
    lat: float
    lng: float
    google_place_id: str | None = None
    primary_category: str
    is_active: bool

    model_config = {"from_attributes": True}


class PoiDetailOut(PoiOut):
    planning_profile: PoiPlanningProfileOut | None = None
    opening_rules: list[PoiOpeningRuleOut] = []
    tags: list[str] = []


class PoiSearchBody(BaseModel):
    query: str = Field(..., min_length=1)
    region: str = "jp"


class PoiImportBody(BaseModel):
    place_id: str
    display_name: str | None = None
    category_override: Literal["lunch", "dinner"] | None = None


class PoiPatch(BaseModel):
    name: str | None = None
    is_active: bool | None = None
