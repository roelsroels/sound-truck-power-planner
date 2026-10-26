# Sound Truck Power Planner

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

## What V1 includes

- Powersoft M-Force/M-Drive infra, DigiMod 3004PFC2 dual-kick, DigiMod 3004PFC4 three-way B&C top example.
- Adjustable numbers and types of cabinet, with independent 230 V L1/L2/L3 assignment.
- Add custom equipment in the UI with reference VA, design VA, PF, evidence and optional weight/footprint.
- Live apparent/real load estimate, generator recommendation and phase-load bars.
- Battery-only nominal energy estimate with duration, usable fraction, inverter efficiency and a programme-demand multiplier.
- Vehicle type, deck dimensions and payload fields; unknown weights/footprints are reported instead of guessed.
- Browser-local project save, JSON import/export and text summary download.
- SQLite-backed shared catalogue with admin-protected create/update/delete API. API reference at `/docs`.

## Project privacy and storage

Saved projects are in your own browser (`localStorage`); JSON export makes them portable. SQLite currently stores the common equipment catalogue only. This avoids anonymous visitors overwriting each other's projects on a public website. Equipment profiles created in a project remain project-local unless an administrator adds them to the shared SQLite catalogue.

### Managing the shared catalogue

Set `ADMIN_TOKEN` to a long, random secret in `.env` **before** deployment if you wish to manage shared equipment via the API. The service is read-only without this setting. Do not place it in JavaScript, URLs, the repo or public docs.

```sh
# on the trusted server, example only; use the actual secure token from .env
curl -X PUT 'http://127.0.0.1:8080/api/v1/catalog/my-cabinet' \
  -H 'Content-Type: application/json' -H 'X-Admin-Token: YOUR_SECRET' \
  --data @my-cabinet.json
```

`my-cabinet.json` must match the `/api/v1/catalog` equipment schema. Don't expose admin access through an untrusted public proxy without HTTPS, rate-limiting and appropriate access control. A future V2/V3 admin UI can be added while preserving the `/api/v1` contract.

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
node --test tests/calc.test.mjs
```

## Calculation policy

The input library stores **AC reference consumption in VA**, **provisional high-load apparent demand in VA**, and assumed PF per cabinet. Audio peak wattage never directly determines mains consumption. The generator recommendation is the next listed kVA class above the maximum of (i) high-load apparent total × headroom, (ii) high-load real-power estimate ÷ generator rated PF × headroom, and (iii) worst-phase high-load apparent demand × 3 × 1.10. This last condition is a conservative proxy and not a substitute for a manufacturer's actual unbalance limits.

Battery energy = reference estimated kW × programme multiplier × event hours ÷ (usable battery fraction × inverter efficiency). Generator surge response, battery power (kW), inverter unbalanced-phase output, harmonics, cable sizing and fuel use are explicitly not certified or automated in this release.

All library values and source links appear in `app/seed.json`; inspect `web/calc.mjs` for the auditable formula implementation. The application deliberately flags missing cabinet weights; it cannot certify axle loads, trailer fit or speaker-stack restraint.

## Roadmap

- **V1.1:** Manufacturer maximum AC input data, measured performance logs, generator fuel profiles and cable schedules (engineer-reviewed only).
- **V2:** Human-reviewed manufacturer lookup, OEM datasheet parsing via optional backend/provider, with provenance and revision history.
- **V3:** Shared multi-user projects, role-based administration, hybrid generator/BESS time simulations, versioned engineering reports, and source-specific transient models.

Hosting contract remains one Docker Compose application, a persistent volume, and an HTTPS reverse proxy. No external database required until concurrency or scale warrants it.

## Licensing

MIT. See [LICENSE](LICENSE).
