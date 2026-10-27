"""Mobile sound-truck planner: read-only public catalogue, optional admin writes."""
import hashlib
import json
import os
from html import escape
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import storage, spec_lookup, library
from .models import Equipment, ReportInput, InspectInput
from .security import SecurityMiddleware, valid_token
from .workers import Worker
from .revision import build_revision

WEB = Path(__file__).resolve().parent.parent / 'web'

def create_app(db_path=None, admin_token=None, security_policy=None):
    path = db_path or os.environ.get('DB_PATH','/data/planner.sqlite3')
    token = admin_token if admin_token is not None else os.environ.get('ADMIN_TOKEN','')
    if token and (not token.isascii() or not token.isprintable() or any(c.isspace() for c in token) or not 32 <= len(token) <= 256):
        raise ValueError('ADMIN_TOKEN must be 32–256 ASCII characters, or empty to disable writes')
    worker = Worker()
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

    docs = os.environ.get('ENABLE_API_DOCS','').lower() == 'true'
    app = FastAPI(title='Sound Truck Power Planner',version='2.0.0',lifespan=lifespan,
                  docs_url='/docs' if docs else None,redoc_url=None,openapi_url='/openapi.json' if docs else None)
    app.state.worker = worker
    allowed_hosts = [h.strip().lower() for h in os.environ.get('ALLOWED_HOSTS','').split(',') if h.strip()]
    if allowed_hosts: allowed_hosts += ['localhost','127.0.0.1','::1']
    app.add_middleware(SecurityMiddleware,token=token,asset_prefix=asset_prefix,
                       allowed_hosts=allowed_hosts,policy=security_policy)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):
        return JSONResponse({'detail':'Invalid request data'},status_code=422)

    def admin_required(value):
        if not valid_token(token,value):
            raise HTTPException(status_code=403,detail='Admin token required')

    async def operation(kind,request):
        status,content,media = await worker.run(kind,await request.body(),path)
        headers = {'Content-Disposition':'attachment; filename="engineering-report.pdf"'} if kind == 'pdf' and status == 200 else {}
        if status == 503:headers['Retry-After']='15'
        return Response(content,status_code=status,media_type=media,headers=headers)

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
    async def specs_inspect(request: Request):
        if os.environ.get('ENABLE_REMOTE_INSPECTION','true').lower() != 'true':
            raise HTTPException(status_code=503,detail='Remote inspection is disabled; use the product library')
        return await operation('inspect',request)

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

    @app.post('/api/v3/library/validate')
    async def validate_library(request: Request):
        return await operation('validate',request)

    @app.post('/api/v3/library/import')
    async def import_library(request: Request, x_admin_token: str | None = Header(default=None)):
        admin_required(x_admin_token)
        return await operation('import',request)

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

    @app.post('/api/v1/reports/engineering.pdf',include_in_schema=False)
    async def engineering_report(request: Request):
        return await operation('pdf',request)

    @app.get('/',include_in_schema=False)
    def index():
        return HTMLResponse(index_html)

    # Relative module imports stay inside this content-versioned directory.
    app.mount(asset_prefix,StaticFiles(directory=web),name='assets')
    # Existing links remain usable, but must not retain an older release in cache.
    app.mount('/assets',StaticFiles(directory=web),name='legacy-assets')
    return app

app = create_app()
