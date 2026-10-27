# Public deployment security

Normal upgrades remain `git pull` followed by `docker compose up -d --build`.
No private hostnames, host paths or proxy configuration are built into the image.
Your existing proxy stays in place. The following controls now ship with the app.

## Request admission

A raw ASGI guard executes before FastAPI reads/parses a body. Administrative
requests need the token before body reads, including invalid JSON. Missing,
non-ASCII, duplicate and oversized token headers fail closed. Configured tokens
must have 32–256 ASCII characters; use a cryptographically random value, not a
phrase. An empty token keeps shared writes disabled. A short configured token now
causes a clear startup error: rotate it before upgrading if administration is used.
A token is never included in responses, browser state, URLs, documentation or logs.

The guard enforces both declared and actual streamed bytes, rejects mismatched or
duplicate Content-Length headers and compressed request bodies, requires JSON for
JSON operations, and allows 15 seconds total to read a body. Limits are decimal:

| Operation | Body limit |
| --- | --- |
| PDF export | 2,000,000 bytes |
| Library validate/shared import | 8,000,000 bytes |
| Other routes, including catalogue writes | 131,072 bytes |

There are at most 24 application requests in flight. One expensive operation
(PDF, library processing or online inspection) runs at once; others receive 503,
rather than waiting in an unbounded queue. Per-client token buckets allow 120
ordinary requests/minute (burst 40), PDF exports 6/minute (burst 3), and library/
inspection operations 4/minute per endpoint (burst 3). Global budgets also apply:
600 ordinary requests/minute (burst 120) and 30 expensive operations/minute
(burst 6). All 429/503 responses include Retry-After. These are starting limits
for a small public planner; monitor legitimate usage before increasing capacity.
Counters are bounded in memory and local to the single server process. Replicas
need shared edge rate limiting; a restart resets the in-process counters.

Validation errors do not echo submitted values or large error arrays. Invalid
input returns a short 422; oversized input 413; slow uploads 408; unsupported
content types 415. None of these errors publishes an imported library.

## Isolated processing

Every expensive operation runs in a disposable spawned child process. Parsing,
validation, model serialization, SQLite library imports and PDF rendering happen
there, keeping the main event loop responsive. A single parent lock reserves the
capacity until the process exits, even when the HTTP request is cancelled.
The parent enforces a 12-second result deadline after spawn, terminates/kills and
joins timed-out workers, and never queues more expensive work. On Linux each child
also has an 8-second CPU limit and a 192 MiB address-space limit. Results are capped
at 10 MB. A fresh process for each job releases its memory and caches on exit.
Worker results use bounded byte framing, not pickle deserialization, and workers
do not retain the admin token environment variable. This is resource isolation,
not a filesystem/network security sandbox: keep input escaping and patches.

Reports use bounded nested project schemas; unknown fields, non-finite numbers,
invalid phase/scenario values and oversized strings are rejected. Existing example,
custom component, meter, venue, fuel and cable data are represented. The report's
existing maximum is 200 units; the interactive planner can still hold 300 units.
Library packs permit at most 20,000 total specification fields in addition to
individual field/product limits; split larger libraries into packs.

## Host, browser and network controls

Malformed/duplicate Host headers are rejected. Routing/cache/security decisions
use the ASGI scope path, never a URL reconstructed from Host. Optional
`ALLOWED_HOSTS` accepts comma-separated exact hosts or `*.example.org` patterns.
Leave it empty to allow any syntactically valid Host; configure it at the real
proxy/application boundary for a specific production site. Loopback names remain
accepted for health checks when a host allowlist is configured.

CSP blocks inline scripts, inline style text/attributes and object embeds. Phase
bars use individual CSSOM width assignments from the trusted external module;
there are no inline style blocks, style attributes in templates, or cssText writes.
The style policy is `style-src 'self'; style-src-attr 'none';`. If a proxy overrides
CSP, update its policy after deploying this frontend.

Frame denial, content sniffing, referrer,
and permission controls are applied to errors as well as successful responses.
API responses are no-store. Only the current content-versioned asset path is
immutable. API documentation is off by default; enable it only when needed with
`ENABLE_API_DOCS=true`.

Manufacturer inspection still accepts only exact official HTTPS product hosts,
blocks redirects and private/reserved DNS results, and bounds returned HTML bytes.
The HTTPS transport connects to the validated public IPs, preserving the original
hostname for TLS certificate verification/SNI and the Host header. It does not
re-resolve the hostname during connect or inherit arbitrary proxy environment
settings. The worker deadline also bounds DNS/slow-response time. Set
`ENABLE_REMOTE_INSPECTION=false` to use the bundled library and source links only.
Library source URLs are never fetched by personal/shared JSON imports.

Project JSON files are capped at 2 MB before browser file reads and field validation.
Library and CSV imports retain their own pre-read size limits. Imported text is
escaped; the PDF builder accepts data, not arbitrary ReportLab layout or macros.

## Container and proxy

Compose retains loopback publishing, non-root execution, read-only root filesystem,
dropped capabilities, no-new-privileges, bounded PID count and noexec/nosuid tmpfs.
Application/static files are owned by root; only the data volume needs runtime
writes. The memory budget is 384 MB to account for the parent plus isolated child;
CPU is capped at one core. Docker JSON logs rotate at 10 MB with three files.
Uvicorn additionally limits concurrent connections/tasks, backlog and keepalive.
These boundaries reduce impact; they do not make the host immune to traffic floods.

`deploy/nginx.example.conf` is a generic example, NOT an installed configuration.
It includes TLS/HSTS, upload/read/connection/rate controls, forwarded-header
replacement and disabled public admin routes. Adapt it into the existing HTTPS
proxy only after reviewing certificate paths, public hostname and any VPN/admin
allowlist. Body limits at the proxy must permit legitimate library/PDF uploads.

`FORWARDED_ALLOW_IPS` defaults to loopback. If the actual proxy peer inside the
container is a Docker bridge address, configure that exact trusted peer/network
and ensure the proxy overwrites client-provided forwarding headers. Do not use `*`
while arbitrary clients can reach the backend. Otherwise clients may share a rate
bucket, or a permissive trust configuration may let clients spoof their bucket key.
TLS, HSTS, firewall rules, DNS and certificate renewal remain proxy/host controls;
pulling the repository cannot configure those on an existing server.

Restrict administrative endpoints to a management network/VPN when enabled, keep
regular SQLite backups, and monitor 408/413/429/503 responses, restarts and OOM logs.
The public configurator does not require accounts.

## Reproducible dependencies and checks

Direct runtime requirements are in `requirements.in`. The complete Python 3.12
runtime resolution, including transitive dependencies and hashes, is committed as
`requirements.txt`. Docker installs only hash-verified binary distributions. The
Python base image and GitHub Actions are pinned to immutable revisions. Weekly
Dependabot updates cover Python, Docker and Actions; review and test those updates.

Regenerate the lock with a trusted current uv installation:

```sh
uv pip compile requirements.in --python-version 3.12 --generate-hashes --output-file requirements.txt
```

CI runs functional/security regression tests, audits the locked Python runtime,
builds the production image and scans OS/language packages for fixable high/critical
vulnerabilities. Unfixed image findings are excluded from that blocking scan and
still need operational review; no scanner proves that a service has no vulnerabilities.
The image revision check remains enabled. Tests cover streamed/declared size limits,
slow bodies, early auth, rate/storage bounds, busy rejection, responsive health,
redacted errors, strict project fields, worker timeout cleanup and DNS pinning.
