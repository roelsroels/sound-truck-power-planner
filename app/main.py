"""Mobile sound-truck planner: read-only public catalogue, optional admin writes."""
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, field_validator

from . import storage
from .report import build_pdf

WEB = Path(__file__).resolve().parent.parent / 'web'

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

    @field_validator('source_url')
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith(('https://','http://')):
            raise ValueError('source URL must be http(s)')
        return value


class ReportInput(BaseModel):
    project: dict
    equipment: list[Equipment] = Field(max_length=250)


def create_app(db_path=None, admin_token=None):
    path = db_path or os.environ.get('DB_PATH','/data/planner.sqlite3')
    token = admin_token if admin_token is not None else os.environ.get('ADMIN_TOKEN','')

    @asynccontextmanager
    async def lifespan(_app):
        storage.initialize(path)
        yield

    app = FastAPI(title='Sound Truck Power Planner', version='1.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
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
        return {'status':'ok', 'schema':1}

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
        return FileResponse(WEB / 'index.html')

    app.mount('/assets',StaticFiles(directory=WEB),name='assets')
    return app

app = create_app()
