"""Mobile sound-truck planner: read-only public catalogue, optional admin writes."""
import hashlib
import json
import os
import secrets
from html import escape
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError, BaseModel, Field, ConfigDict, field_validator

from . import storage, spec_lookup, library
from .report import build_pdf
from .revision import build_revision

WEB = Path(__file__).resolve().parent.parent / 'web'

class LibraryComponent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: str = Field(pattern=library.ID)
    manufacturer: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=150)
    variant: str = Field(default='', max_length=100)
    quantity: int = Field(ge=1, le=100)
    source_url: str = Field(max_length=1000)
    _url = field_validator('source_url')(library.http_url)


class Equipment(BaseModel):
    model_config = ConfigDict(extra='forbid')
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
        if value and not value.startswith(('https://','http://')):
            raise ValueError('source URL must be http(s)')
        return value


class InspectInput(BaseModel):
    url: str = Field(min_length=12,max_length=750)


class ReportInput(BaseModel):
    project: dict
    equipment: list[Equipment] = Field(max_length=250)


def create_app(db_path=None, admin_token=None):
    path = db_path or os.environ.get('DB_PATH','/data/planner.sqlite3')
    token = admin_token if admin_token is not None else os.environ.get('ADMIN_TOKEN','')
    web = WEB
    digest = hashlib.sha256()
    for asset in sorted(web.rglob('*')):
        if asset.is_file():
            digest.update(asset.relative_to(web).as_posix().encode())
            digest.update(b'\0')
            digest.update(asset.read_bytes())
            digest.update(b'\0')
    frontend_revision = digest.hexdigest()[:16]
    asset_prefix = f'/assets/{frontend_revision}'
    source = build_revision()
    repository = 'https://github.com/roelsroels/sound-truck-power-planner'
    source_link = repository + '/tree/' + quote(source['branch'], safe='') if source['branch'] not in ('unknown', 'detached') else repository
    revision_link = repository + '/commit/' + source['revision'] if source['revision'] != 'unknown' else repository
    index_html = (web / 'index.html').read_text().replace('/assets/', asset_prefix + '/')
    index_html = index_html.replace('__SOURCE_LINK__', escape(source_link, quote=True))
    index_html = index_html.replace('__REVISION_LINK__', escape(revision_link, quote=True))
    index_html = index_html.replace('__SOURCE_BRANCH__', escape(source['branch']))
    index_html = index_html.replace('__SOURCE_REVISION__', escape(source['revision'][:7]))

    @asynccontextmanager
    async def lifespan(_app):
        storage.initialize(path)
        yield

    app = FastAPI(title='Sound Truck Power Planner', version='2.0.0', lifespan=lifespan)

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        request_path = request.url.path
        if request_path in ('/', '/api/health') or request_path.startswith('/api/v3/library'):
            response.headers['Cache-Control'] = 'no-store'
        elif request_path.startswith('/assets/'):
            response.headers['Cache-Control'] = (
                'public, max-age=31536000, immutable'
                if request_path.startswith(asset_prefix + '/') and response.status_code in (200,304)
                else 'no-store'
            )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        return response

    def admin_required(value):
        if not token or not value or not secrets.compare_digest(token, value):
            raise HTTPException(status_code=403,detail='Admin token required; catalogue is read-only without ADMIN_TOKEN')

    @app.get('/api/health')
    def health():
        return {'status':'ok', 'schema':1, 'frontend_revision':frontend_revision, 'source':source}

    @app.get('/api/v2/specs/search')
    def specs_search(model: str):
        try:
            return {"items": spec_lookup.search_models(model)}
        except ValueError as exc:
            raise HTTPException(status_code=422,detail=str(exc))

    @app.post('/api/v2/specs/inspect')
    def specs_inspect(body: InspectInput, request: Request):
        try:
            spec_lookup.rate_limit(request.client.host if request.client else None)
            return spec_lookup.inspect(body.url)
        except ValueError as exc:
            message=str(exc)
            code=429 if "limit reached" in message else (422 if "Only official" in message or "Invalid" in message else 502)
            raise HTTPException(status_code=code,detail=message)

    @app.get('/api/v3/library')
    def product_library():
        return library.manifest(path)

    @app.get('/api/v3/library/schema')
    def library_schema():
        return library.Pack.model_json_schema()

    @app.get('/api/v3/library/products/{id}')
    def library_product(id: str):
        product = library.snapshot(path)[1].get(id)
        if product is None:
            raise HTTPException(status_code=404, detail='Product not found')
        return product

    async def read_pack(request):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 8_000_000:
                raise HTTPException(status_code=413, detail='Library file exceeds 8 MB')
        try:
            return library.Pack.model_validate_json(content)
        except ValidationError as exc:
            first = exc.errors(include_input=False, include_url=False)[0]
            raise HTTPException(status_code=422, detail='Invalid library: ' + '.'.join(map(str, first['loc'])) + ': ' + first['msg'])

    @app.post('/api/v3/library/validate')
    async def validate_library(request: Request):
        # Validation only: browser imports never alter the public library.
        return (await read_pack(request)).model_dump(mode='json')

    @app.post('/api/v3/library/import')
    async def import_library(request: Request, x_admin_token: str | None = Header(default=None)):
        admin_required(x_admin_token)
        return library.import_pack(path, await read_pack(request))

    @app.get('/api/v1/catalog',response_model=list[Equipment])
    def catalogue():
        return storage.all_equipment(path)

    @app.get('/api/v1/example')
    def example():
        return json.loads(storage.EXAMPLE.read_text())

    @app.put('/api/v1/catalog/{id}',response_model=Equipment)
    def upsert(id:str, item:Equipment, x_admin_token:str|None=Header(default=None)):
        admin_required(x_admin_token)
        if id!=item.id:
            raise HTTPException(status_code=400,detail='Path ID and equipment ID differ')
        storage.put_equipment(path,item.model_dump())
        return item

    @app.delete('/api/v1/catalog/{id}')
    def delete(id:str, x_admin_token:str|None=Header(default=None)):
        admin_required(x_admin_token)
        if not storage.delete_equipment(path,id):
            raise HTTPException(status_code=404,detail='Not found')
        return {'ok':True}

    @app.post('/api/v1/reports/engineering.pdf', include_in_schema=False)
    def engineering_report(body: ReportInput):
        try:
            document = build_pdf(body.project, [e.model_dump() for e in body.equipment])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)[:180])
        return Response(
            content=document, media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="engineering-report.pdf"',
                     'Cache-Control': 'no-store'}
        )

    @app.get('/',include_in_schema=False)
    def index():
        return HTMLResponse(index_html)

    # Relative module imports stay inside this content-versioned directory.
    app.mount(asset_prefix,StaticFiles(directory=web),name='assets')
    # Existing links remain usable, but must not retain an older release in cache.
    app.mount('/assets',StaticFiles(directory=web),name='legacy-assets')
    return app

app = create_app()
