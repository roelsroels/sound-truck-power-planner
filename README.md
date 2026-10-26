# Sound Truck Power Planner

**Version 2.0** — equipment/source review, real-power measurements and supplier fuel curves, in the original Docker + SQLite footprint.

A compact, self-hosted electrical **planning** tool for high-output mobile sound systems. Docker Compose deployment, persistent SQLite equipment catalogue, client-local projects, and a preloaded Powersoft/B&C test system. Public access requires no account; *catalogue changes* require an optional administrator token.

> **Important:** This is a planning calculator, not an approved electrical installation design. The supplied high-load values for DigiMod modules are engineering allowances, not published maximum AC input ratings. Verify complete active-cabinet input protection and consumption, generator transient performance, fault protection, cabling, earthing/bonding and moving-vehicle operation with qualified professionals.

## Start

```sh
git clone https://github.com/roelsroels/sound-truck-power-planner.git
cd sound-truck-power-planner
cp .env.example .env
# Optionally set ADMIN_TOKEN in .env (see below)
docker compose up -d --build
```

Visit `http://127.0.0.1:8080`. Bind your own HTTPS reverse proxy to `127.0.0.1:8080`. No reverse proxy or TLS settings are hard-coded; existing hosting stays unchanged across upgrades. The app uses the named `planner_data` volume for `/data/planner.sqlite3`.

## What the current app includes

- Powersoft M-Force/M-Drive infra, DigiMod 3004PFC2 dual-kick, DigiMod 3004PFC4 three-way B&C top example.
- Adjustable numbers and types of cabinet, with independent 230 V L1/L2/L3 assignment.
- Add custom equipment in the UI with reference VA, design VA, PF, evidence and optional weight/footprint.
- Live apparent/real load estimate, generator recommendation and phase-load bars.
- Battery-only nominal energy estimate with duration, usable fraction, inverter efficiency and a programme-demand multiplier.
- Vehicle type, deck dimensions and payload fields; unknown weights/footprints are reported instead of guessed.
- Browser-local project save, JSON import/export and text summary download.
- Project-specific cabinet profile edits without changing the public shared catalogue.
- One-click high-load phase redistribution (must be verified against actual measured currents).
- Generator-only, battery-only and hybrid scenario screening, installed BESS/inverter capacity, runtime and optional supplier fuel-rate estimates.
- Truck payload screen with optional generator, battery and other load masses. Missing weights remain explicit.
- Designed multi-page **engineering PDF export** with KPI summary, per-phase load visualisation, equipment schedule, vehicle assessment and source/assumption disclosure.
- SQLite-backed shared catalogue with admin-protected create/update/delete API. API reference at `/docs`.

## V2 field workflows

**Manufacturer search/review:** Search for a model in the curated official B&C/Powersoft index. Use **Inspect official page** (or paste a supported HTTPS product URL) to request a bounded, read-only inspection from the running application. Only these exact official product hosts and product paths are accepted; remote fetches are timeout- and size-limited, rate-limited, and do not follow redirects. If a manufacturer changes its page structure or blocks access, inspection reports an error; the official source link remains available for manual verification. After reviewing the evidence, **Apply reviewed source** creates a project-local copy of the selected cabinet and attaches its evidence. **It does not overwrite reference or high-load VA:** speaker/audio wattage is not mains consumption. The shared catalogue remains read-only to visitors.

**Measured power:** Export real-power measurements from your own meter with exact CSV columns `timestamp,l1_kw,l2_kw,l3_kw`. Every row needs an ISO-8601 timestamp with timezone, ascending time and nonnegative kW for three phases. The browser computes a time-weighted trapezoidal energy estimate and sample-based peaks; raw CSV never leaves your browser. The saved project contains summary statistics. Compare the result to the equipment reference and optionally approve a new programme multiplier. Metered real kW still does not certify short power transients, power factor, inverter sizing or generator response.

**Fuel curves:** Add supplier-reported litres/hour at 25%, 50%, 75% and 100% generator prime real-power load, plus model/source notes. V2 interpolates only between published points; it deliberately withholds predictions outside 25–100% or for non-monotonic/incomplete curves. An imported average real-power measurement is preferred when present; otherwise reference demand is used. Figures are indicative before reserve.

**Cable worksheet:** Optionally enter cable length, protective-device rating, conductor cross-section and engineer-reviewed flag for each load. The application does not select conductor sizes or certify fault protection. Those fields appear in the PDF as an electrician's checklist.

**PDF export:** Engineering PDFs append measured sample statistics, fuel-curve values/interpolation and cable handoff notes. Projects and reports remain temporary on the server; no extra database table or permanent uploaded file is created.

## Project privacy and storage

Saved projects are in your own browser (`localStorage`); JSON export makes them portable. When you request a PDF, the browser sends the current project and its active equipment profiles to the self-hosted report endpoint; the PDF is generated in memory and returned without saving a project or report to SQLite. SQLite currently stores the common equipment catalogue only. V2 field logs and site decisions remain project-local; the source inspector does not store source pages or visitor projects. This avoids anonymous visitors overwriting each other's projects on a public website. Equipment profiles created in a project remain project-local unless an administrator adds them to the shared SQLite catalogue.

### Managing the shared catalogue

Set `ADMIN_TOKEN` to a long, random secret in `.env` **before** deployment if you wish to manage shared equipment via the API. The service is read-only without this setting. Do not place it in JavaScript, URLs, the repo or public docs.

```sh
# on the trusted server, example only; use the actual secure token from .env
curl -X PUT 'http://127.0.0.1:8080/api/v1/catalog/my-cabinet' \
  -H 'Content-Type: application/json' -H 'X-Admin-Token: YOUR_SECRET' \
  --data @my-cabinet.json
```

`my-cabinet.json` must match the `/api/v1/catalog` equipment schema. Don't expose admin access through an untrusted public proxy without HTTPS, rate-limiting and appropriate access control. A future V2/V3 admin UI can be added while preserving the `/api/v1` contract.

## V1.1 PDF export

Use **Download engineering PDF** from the browser. This creates a report with deliberately prominent planning-only warnings. There is no external PDF service, CDN, account, or new persistent volume. The server-side PDF endpoint is `POST /api/v1/reports/engineering.pdf`, with bounded input validation; it is public so normal visitors can export their own projects. Nginx can enforce its existing request-size and rate limits. The values are independent calculations from the submitted equipment profiles, not browser-supplied result totals.

## Version upgrades / backup

```sh
docker compose pull  # Only relevant when using a published image
docker compose up -d --build
# Backup while the container is stopped, or use SQLite's online backup API
```

Keep the **named volume** `planner_data` intact when upgrading; `docker compose down -v` intentionally deletes it. For a safe backup:

```sh
docker compose stop planner
mkdir -p backups
docker run --rm -v sound-truck-power-planner_planner_data:/from:ro -v "$PWD/backups":/to busybox sh -c 'cp /from/planner.sqlite3 /to/planner.sqlite3'
docker compose start planner
```

The precise Compose volume name depends on your Compose project name; check `docker volume ls` first. SQLite schema migrations will be versioned as the app evolves.

## Running tests

```sh
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
node --test tests/calc.test.mjs tests/v2.test.mjs tests/lookup.test.mjs
```

## Calculation policy

The input library stores **AC reference consumption in VA**, **provisional high-load apparent demand in VA**, and assumed PF per cabinet. Audio peak wattage never directly determines mains consumption. The generator recommendation is the next listed kVA class above the maximum of (i) high-load apparent total × headroom, (ii) high-load real-power estimate ÷ generator rated PF × headroom, and (iii) worst-phase high-load apparent demand × 3 × 1.10. This last condition is a conservative proxy and not a substitute for a manufacturer's actual unbalance limits.

Battery energy = reference estimated kW × programme multiplier × event hours ÷ (usable battery fraction × inverter efficiency). Generator surge response, battery power (kW), inverter unbalanced-phase output, harmonics, cable sizing and fuel use are explicitly not certified or automated in this release.

All library values and source links appear in `app/seed.json`; inspect `web/calc.mjs` for the auditable formula implementation. The application deliberately flags missing cabinet weights; it cannot certify axle loads, trailer fit or speaker-stack restraint. Battery inverter sizing is a numerical screening only and never guarantees phase-unbalance, fault protection, surge capability or BESS/generator synchronisation.

## Roadmap

- **V1.1 (implemented):** Project-local cabinet editing, power-source screening, phase distribution helper, source/vehicle weight inputs and PDF reports.
- **V2 (implemented):** Guarded live manufacturer source inspection with human review, browser-local meter CSV summaries, documented fuel curves and preliminary cable handoff.
- **V3 (future):** Shared projects only if needed, manufacturer integrations where supported, hybrid generator/BESS time simulations and richer source-specific transient models.

Hosting contract remains one Docker Compose application, a persistent volume, and an HTTPS reverse proxy. No external database required until concurrency or scale warrants it.

## Licensing

MIT. See [LICENSE](LICENSE).
