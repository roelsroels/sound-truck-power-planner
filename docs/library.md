# Product library and manufacturer imports

The library is separate from the planner's mains-load catalogue. Drivers, passive
cabinets, amplifiers, active cabinets and accessories have independent product
records. Different impedance/model variants have different stable IDs. Each
record retains its official source, source retrieval date, published specification
fields, test-condition notes, and available PDF links. Images, PDF files and
marketing descriptions are not redistributed.

The bundled snapshot contains B&C's current and archived component listings and
Powersoft's published amplifier/transducer listings. Specifications mean the
fields published on those product pages: they are not a claim that every figure
from every PDF has been transcribed or independently verified. Consult the linked
original datasheets, including revision-specific conditions, before engineering a
system. New releases after the snapshot need a fresh import. Raw manufacturer
labels and conditions are retained in their original language.

## Using the configurator

Choose **Browse product library** in either view. Filter by manufacturer, product
type, model or impedance, and optionally include archived products. Open a product
to inspect specifications/documents and choose **Use in power profile**.

Build one profile per separately supplied AC load. An amplifier powering several
passive cabinets belongs in ONE profile, with those cabinets/drivers as components;
do not add that same amplifier again per passive cabinet. Quantity on the resulting
profile duplicates the whole AC-fed assembly. An active cabinet is its own profile.
Component quantities and source references survive project save/JSON export.
The new profile also becomes a reusable entry in that project's equipment menu.

Confirm channel wiring, combined impedance, bridging, limiter settings and amplifier
compatibility separately: the library does not automatically approve combinations.
DC/PoE amplifiers are identified and cannot serve as an AC source in the builder.
Use the consumption of their upstream supply in a custom electrical profile.

Speaker power handling and amplifier output W are NEVER converted into mains VA.
Only explicit published VA consumption is offered as an initial reference value,
with its operating conditions. Missing planning VA and power factor must be supplied,
and a basis is required. A new user-built profile is marked estimated. Driver/module
weight is not silently used as the weight of the completed cabinet.

## Another manufacturer, including complete cabinets

There is no manufacturer allowlist in the schema or frontend. For example,
Funktion-One can be imported as `passive_cabinet` or `active_cabinet`, rather than
pretending complete cabinets are raw drivers. Impedance options need separate
product IDs. Use `specs` for any additional technical fields: adding a manufacturer
or a new specification does not require UI/database migrations.

Download the template from the library's Advanced import section, or use
`web/library-template.json`. Replace the example manufacturer/product and source
URLs with actual published data. The machine-readable JSON Schema is available at
`GET /api/v3/library/schema`.

Pack format:

- `schema_version`: currently `1`.
- `manufacturers`: stable lowercase `id`, display `name`, HTTP(S) `website`.
- `products`: globally stable `id` prefixed by `manufacturer_id` plus `-`,
  `manufacturer_id`, `model`, `variant`, `kind`, `category`, `power_input`, `status`,
  `source_url`, `datasheet_urls`, ISO `checked_at`, `specs`, and optional `electrical`.
- `kind`: `driver`, `amplifier`, `passive_cabinet`, `active_cabinet`, `accessory`.
- `power_input`: `ac`, `dc`, `none`, or `unknown`; use `none` for passive products.
- `status`: `current`, `archived`, or `unknown`.
- Every spec has a unique stable `key`, `section`, `label`, string `value`, and
  optional `notes`. Preserve units and measurement conditions in the value/notes.
- `electrical` is null when unavailable. Only AC load products can declare it;
  its nullable `reference_va`, `design_va`, `power_factor` require a documented
  `basis`. Do not put speaker/output power here.

Validate a pack without altering any database:

```sh
python -m app.library manufacturer.json
```

### Personal browser import

Advanced → Product library → Import another manufacturer accepts a JSON pack up
to 8 MB and 20,000 specification fields. The server validates it without writing to the public library or fetching
its URLs. The browser merges by product ID and saves the imported library locally.
Export the browser library to back it up or move it to another browser. A quota
failure leaves the previously saved library intact. Browser libraries are separate
from project exports, which contain the selected component references and mains
profile, not the complete manufacturer library.

### Shared imports

For a reviewed, version-controlled library, add the validated pack under
`app/library_data/` and rebuild the image. Do not repeat a product ID across packs.
New bundled packs appear after rebuilding without replacing existing project data.

Alternatively, an administrator may POST the same pack to
`/api/v3/library/import` with the existing `X-Admin-Token` header, or run:

```sh
python -m app.library manufacturer.json --db /data/planner.sqlite3
```

Authenticated/CLI imports upsert in one SQLite transaction. They are persistent
overrides of bundled records; they do not delete unrelated products or overwrite
the existing mains-load catalogue. Reimport stable IDs to update specifications.
The public UI cannot write to the shared catalogue. Supplying credentials inside
source URLs is rejected; source links are not fetched by the library API.

## Refreshing the official snapshot

From a development checkout with network access:

```sh
python scripts/import_manufacturers.py --cache work/manufacturer-cache --output app/library_data
```

The importer uses only Python's standard library, fetches from the two official
hosts, caches pages, limits concurrency, retries transient failures, and fails if
page structures no longer match. Use an empty cache for a fresh snapshot. A cached
page retains its original retrieval date. Review changed counts, variants, sources
and specifications before committing; an importer is not independent verification.
Additional manufacturers can supply the neutral JSON format directly or have a
new offline adapter added here. No scraper runs during normal app use.

Shared administration and processing budgets are documented in [security controls](security.md).
