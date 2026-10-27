"""Bounded schemas for untrusted planning data."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import library

class LibraryComponent(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    product_id: str = Field(pattern=library.ID)
    manufacturer: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=150)
    variant: str = Field(default='', max_length=100)
    quantity: int = Field(ge=1, le=100)
    source_url: str = Field(max_length=1000)
    _url = field_validator('source_url')(library.http_url)


class Equipment(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{1,63}$')
    name: str = Field(min_length=1,max_length=120)
    category: str = Field(min_length=1,max_length=30)
    drivers: str = Field(default='',max_length=250)
    amplifier: str = Field(default='',max_length=250)
    reference_va: float = Field(ge=0,le=1_000_000)
    design_va: float = Field(ge=0,le=1_000_000)
    power_factor: float = Field(gt=0,le=1)
    weight_kg: float | None = Field(default=None,ge=0,le=100_000)
    width_m: float | None = Field(default=None,ge=0,le=100)
    depth_m: float | None = Field(default=None,ge=0,le=100)
    source_url: str = Field(default='',max_length=1000)
    reference_basis: str = Field(default='',max_length=500)
    design_basis: str = Field(default='',max_length=500)
    confidence: str = Field(default='estimate',pattern=r'^(verified|mixed|estimate)$')
    library_components: list[LibraryComponent] = Field(default_factory=list, max_length=64)

    @field_validator('source_url')
    @classmethod
    def safe_url(cls, value):
        return library.http_url(value) if value else ''


class Bounded(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Unit(Bounded):
    equipment_id: str = Field(min_length=1,max_length=64)
    phase: Literal['L1','L2','L3']

class Vehicle(Bounded):
    type: str = Field(default='',max_length=150)
    deck_length_m: float | None = Field(default=None,ge=0,le=100)
    deck_width_m: float | None = Field(default=None,ge=0,le=100)
    payload_kg: float | None = Field(default=None,ge=0,le=100000)
    generator_weight_kg: float | None = Field(default=None,ge=0,le=100000)
    battery_weight_kg: float | None = Field(default=None,ge=0,le=100000)
    other_weight_kg: float | None = Field(default=None,ge=0,le=100000)

class Venue(Bounded):
    L1: float | None = Field(default=None,ge=0,le=10000)
    L2: float | None = Field(default=None,ge=0,le=10000)
    L3: float | None = Field(default=None,ge=0,le=10000)

class Meter(Bounded):
    kind: Literal['measured-ac-real-power']
    source: str = Field(default='',max_length=100)
    samples: int = Field(ge=2,le=5000)
    minutes: float = Field(ge=0,le=300000)
    average_kw: float = Field(ge=0,le=3000)
    observed_peak_kw: float = Field(ge=0,le=3000)
    energy_kwh: float = Field(ge=0,le=10000000)
    phase_peak_kw: list[Annotated[float,Field(ge=0,le=1000)]] = Field(default_factory=list,max_length=3)
    largest_gap_min: float = Field(ge=0,le=60)
    start: str = Field(default='',max_length=40)
    end: str = Field(default='',max_length=40)

class Fuel(Bounded):
    model: str = Field(default='',max_length=180)
    source: str = Field(default='',max_length=500)
    p25: float | None = Field(default=None,ge=0,le=1000)
    p50: float | None = Field(default=None,ge=0,le=1000)
    p75: float | None = Field(default=None,ge=0,le=1000)
    p100: float | None = Field(default=None,ge=0,le=1000)

class Circuit(Bounded):
    length_m: float | None = Field(default=None,ge=0,le=10000)
    breaker_a: float | None = Field(default=None,ge=0,le=10000)
    cable_mm2: float | None = Field(default=None,ge=0,le=10000)
    engineer_reviewed: bool = False

class Project(Bounded):
    version: Literal[1] = 1
    name: str = Field(default='Project',min_length=1,max_length=120)
    language: Literal['en','nl'] = 'en'
    setup_mode: Literal['mobile','fixed'] = 'mobile'
    power_mode: Literal['generator','battery','hybrid'] = 'generator'
    duration_h: float = Field(default=8,ge=.1,le=100)
    generator_kva: float = Field(default=40,gt=0,le=10000)
    voltage_v: float = Field(default=230,ge=1,le=1000)
    generator_pf: float = Field(default=.8,gt=0,le=1)
    headroom_pct: float = Field(default=25,ge=0,le=300)
    battery_use_fraction: float = Field(default=.8,gt=0,le=1)
    inverter_efficiency: float = Field(default=.92,gt=0,le=1)
    battery_installed_kwh: float = Field(default=0,ge=0,le=1000000)
    inverter_kva: float = Field(default=0,ge=0,le=10000)
    fuel_rate_lph: float | None = Field(default=None,ge=0,le=1000)
    program_multiplier: float = Field(default=1,gt=0,le=100)
    vehicle: Vehicle = Field(default_factory=Vehicle)
    venue_supply: Venue | None = None
    units: list[Unit] = Field(max_length=200)
    custom_equipment: list[Equipment] = Field(default_factory=list,max_length=250)
    meter_summary: Meter | None = None
    generator_fuel_curve: Fuel | None = None
    circuit_notes: dict[Annotated[str,Field(pattern=r'^[0-9]{1,3}$')],Circuit] = Field(default_factory=dict,max_length=300)

class ReportInput(Bounded):
    project: Project
    equipment: list[Equipment] = Field(max_length=250)

class InspectInput(Bounded):
    url: str = Field(min_length=12,max_length=750)
