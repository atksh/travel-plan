from __future__ import annotations

from pydantic import BaseModel, Field


class PlaceVisitProfileOut(BaseModel):
    stay_min_minutes: int
    stay_preferred_minutes: int
    stay_max_minutes: int
    price_band: str | None = None
    rating: float | None = None
    accessibility_notes: str | None = None


class PlaceAvailabilityRuleOut(BaseModel):
    weekday: int | None = None
    open_minute: int
    close_minute: int
    valid_from: str | None = None
    valid_to: str | None = None
    last_admission_minute: int | None = None
    closed_flag: bool


class PlaceSourceRecordOut(BaseModel):
    provider: str
    provider_place_id: str | None = None
    source_url: str | None = None
    fetched_at: str
    parser_version: str


class PlaceSummaryOut(BaseModel):
    id: int
    name: str
    lat: float
    lng: float
    source: str
    archived: bool
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)


class PlaceDetailOut(PlaceSummaryOut):
    visit_profile: PlaceVisitProfileOut | None = None
    availability_rules: list[PlaceAvailabilityRuleOut] = Field(default_factory=list)
    source_records: list[PlaceSourceRecordOut] = Field(default_factory=list)
    notes: str | None = None


class PlaceListOut(BaseModel):
    items: list[PlaceSummaryOut] = Field(default_factory=list)
    next_cursor: str | None = None


class PlaceSearchResultOut(BaseModel):
    provider: str
    provider_place_id: str
    name: str
    lat: float
    lng: float
    primary_type: str | None = None
    rating: float | None = None
    price_level: str | None = None


class PlaceSearchResponseOut(BaseModel):
    results: list[PlaceSearchResultOut] = Field(default_factory=list)


class BoundsIn(BaseModel):
    north: float
    south: float
    east: float
    west: float


class PlaceListQuery(BaseModel):
    q: str | None = None
    tags: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    source: str | None = None
    archived: bool | None = None


class PlaceSearchTextIn(BaseModel):
    query: str = Field(..., min_length=1)
    region: str = "jp"


class PlaceSearchAreaIn(BaseModel):
    center: dict[str, float] | None = None
    radius_m: int | None = Field(default=None, ge=1)
    bounds: BoundsIn | None = None
    included_types: list[str] = Field(default_factory=list)


class PlaceImportIn(BaseModel):
    provider: str
    provider_place_id: str
    overrides: dict = Field(default_factory=dict)


class PlaceCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    lat: float
    lng: float
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    visit_profile: dict | None = None
    availability_rules: list[dict] = Field(default_factory=list)
    note: str | None = None


class PlacePatchIn(BaseModel):
    name: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    traits: list[str] | None = None
    visit_profile: dict | None = None
    availability_rules: list[dict] | None = None
    notes: str | None = None
    archived: bool | None = None
