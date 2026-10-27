"""Manufacturer-neutral product packs, separate from calculated AC load profiles."""
import argparse
from datetime import date
from functools import lru_cache
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from . import storage

ID = r'^[a-z0-9][a-z0-9_.-]{1,119}$'


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


def http_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
        raise ValueError('Expected an HTTP(S) URL without credentials')
    return value


class Manufacturer(Record):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    website: str = Field(max_length=1000)
    _url = field_validator('website')(http_url)


class Specification(Record):
    key: str = Field(min_length=1, max_length=160)
    section: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=250)
    value: str = Field(max_length=4000)
    notes: str = Field(default='', max_length=6000)


class Electrical(Record):
    reference_va: float | None = Field(default=None, ge=0, le=1_000_000)
    design_va: float | None = Field(default=None, ge=0, le=1_000_000)
    power_factor: float | None = Field(default=None, gt=0, le=1)
    basis: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def ordered(self):
        if self.reference_va is not None and self.design_va is not None and self.design_va < self.reference_va:
            raise ValueError('Design VA must be at least reference VA')
        return self


class Product(Record):
    id: str = Field(pattern=ID)
    manufacturer_id: str = Field(pattern=ID)
    model: str = Field(min_length=1, max_length=150)
    variant: str = Field(default='', max_length=100)
    kind: Literal['driver','amplifier','passive_cabinet','active_cabinet','accessory']
    category: str = Field(min_length=1, max_length=100)
    power_input: Literal['ac','dc','none','unknown'] = 'unknown'
    status: Literal['current','archived','unknown'] = 'unknown'
    source_url: str = Field(max_length=1000)
    datasheet_urls: list[str] = Field(default_factory=list, max_length=40)
    checked_at: date
    specs: list[Specification] = Field(default_factory=list, max_length=600)
    electrical: Electrical | None = None
    _source = field_validator('source_url')(http_url)

    @field_validator('datasheet_urls')
    @classmethod
    def documents(cls, values):
        return [http_url(v) for v in values]

    @model_validator(mode='after')
    def passive_is_not_mains(self):
        if not self.id.startswith(self.manufacturer_id + '-'):
            raise ValueError('Product IDs must start with manufacturer_id followed by a hyphen')
        if (self.kind not in ('amplifier','active_cabinet') or self.power_input == 'dc') and self.electrical is not None:
            raise ValueError('Passive components cannot declare mains consumption')
        if len({s.key for s in self.specs}) != len(self.specs):
            raise ValueError('Duplicate specification keys')
        return self


class Pack(Record):
    schema_version: Literal[1]
    manufacturers: list[Manufacturer] = Field(min_length=1, max_length=100)
    products: list[Product] = Field(min_length=1, max_length=5000)

    @model_validator(mode='after')
    def references(self):
        if sum(len(p.specs) for p in self.products) > 20000:
            raise ValueError('A pack can contain at most 20000 specification fields')
        ids = {m.id for m in self.manufacturers}
        if len(ids) != len(self.manufacturers) or len({p.id for p in self.products}) != len(self.products):
            raise ValueError('Duplicate manufacturer or product IDs')
        if any(p.manufacturer_id not in ids for p in self.products):
            raise ValueError('Each product needs a manufacturer in this pack')
        return self


@lru_cache(maxsize=1)
def bundled():
    manufacturers, products = {}, {}
    for file in sorted(Path(__file__).with_name('library_data').glob('*.json')):
        pack = Pack.model_validate_json(file.read_text()).model_dump(mode='json')
        for manufacturer in pack['manufacturers']:
            old = manufacturers.get(manufacturer['id'])
            if old and old != manufacturer: raise ValueError('Conflicting bundled manufacturer')
            manufacturers[manufacturer['id']] = manufacturer
        for product in pack['products']:
            if product['id'] in products: raise ValueError('Duplicate bundled product: ' + product['id'])
            products[product['id']] = product
    return manufacturers, products


def snapshot(path):
    manufacturers, products = map(dict, bundled())
    for item in storage.library_records(path):
        if item['record_type'] == 'manufacturer': manufacturers[item['id']] = item['data']
        else: products[item['id']] = item['data']
    return manufacturers, products


def manifest(path):
    manufacturers, products = snapshot(path)
    return {'schema_version': 1, 'manufacturers': sorted(manufacturers.values(), key=lambda m: m['name']),
            'products': [{**{k: v for k, v in p.items() if k not in ('specs','datasheet_urls','electrical')},
                          'spec_count': len(p['specs'])} for p in sorted(products.values(), key=lambda p: (p['manufacturer_id'], p['model'], p['variant']))]}


def import_pack(path, pack):
    storage.put_library_pack(path, pack.model_dump(mode='json'))
    return {'manufacturers': len(pack.manufacturers), 'products': len(pack.products)}


def main():
    parser = argparse.ArgumentParser(description='Validate or import a version-1 manufacturer library JSON pack.')
    parser.add_argument('pack', type=Path)
    parser.add_argument('--db', help='SQLite database to import into; omit to validate only')
    args = parser.parse_args(); pack = Pack.model_validate_json(args.pack.read_text())
    if args.db:
        storage.initialize(args.db); print(json.dumps(import_pack(args.db, pack)))
    else: print(f'Valid library: {len(pack.manufacturers)} manufacturers, {len(pack.products)} products')


if __name__ == '__main__': main()
