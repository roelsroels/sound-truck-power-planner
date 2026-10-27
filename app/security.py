"""Early ASGI admission controls. Counters are bounded and local to one worker."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from fnmatch import fnmatchcase
import ipaddress
import json
import logging
import re
import secrets
import time
from starlette.datastructures import MutableHeaders

log = logging.getLogger(__name__)
PDF = '/api/v1/reports/engineering.pdf'
VALIDATE = '/api/v3/library/validate'
IMPORT = '/api/v3/library/import'
INSPECT = '/api/v2/specs/inspect'
HEAVY = {PDF, VALIDATE, IMPORT, INSPECT}


@dataclass(frozen=True)
class Policy:
    body_timeout: float = 15
    general_body: int = 131072
    report_body: int = 2_000_000
    library_body: int = 8_000_000
    connections: int = 24
    rate_multiplier: float = 1


class Buckets:
    def __init__(self, capacity=2048, clock=time.monotonic):
        self.items = OrderedDict(); self.capacity = capacity; self.clock = clock

    def allow(self, key, per_minute, burst):
        now = self.clock()
        tokens, before = self.items.pop(key, (float(burst), now))
        tokens = min(float(burst), tokens + max(0, now-before)*per_minute/60)
        allowed = tokens >= 1
        self.items[key] = (tokens-1 if allowed else tokens, now)
        while len(self.items) > self.capacity:
            self.items.popitem(last=False)
        return allowed


def valid_token(configured, supplied):
    if not configured or not supplied or len(supplied) > 256:
        return False
    try:
        raw = supplied.encode('ascii') if isinstance(supplied, str) else supplied
        if not raw.isascii(): return False
        return secrets.compare_digest(configured.encode('ascii'), raw)
    except (UnicodeError, TypeError):
        return False


def valid_host(raw, allowed):
    try:
        host = raw.decode('ascii').lower()
        if host.startswith('['):
            match = re.fullmatch(r'\[([^\]]+)\](?::([0-9]{1,5}))?', host)
            if not match: return False
            ipaddress.IPv6Address(match[1]); name = match[1]; port = match[2]
        else:
            match = re.fullmatch(r'([^:]+)(?::([0-9]{1,5}))?', host)
            if not match: return False
            name, port = match[1], match[2]
            if len(name) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in name.rstrip('.').split('.')):
                return False
        if port and not 0 < int(port) <= 65535: return False
        return not allowed or any(fnmatchcase(name.rstrip('.'), value) for value in allowed)
    except (UnicodeError, ValueError):
        return False


class SecurityMiddleware:
    def __init__(self, app, *, token, asset_prefix, allowed_hosts=(), policy=None):
        self.app = app; self.token = token; self.asset_prefix = asset_prefix
        self.allowed_hosts = tuple(allowed_hosts); self.policy = policy or Policy()
        self.buckets = Buckets(); self.globals = Buckets(capacity=8); self.active = 0; self.heavy = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']  # Never reconstruct a security decision from Host.
        method = scope['method']; started = False
        async def secured_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                headers = MutableHeaders(scope=message)
                if message['status'] in (429,503): headers.setdefault('Retry-After','15')
                headers['X-Content-Type-Options'] = 'nosniff'
                headers['X-Frame-Options'] = 'DENY'
                headers['Referrer-Policy'] = 'no-referrer'
                headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
                headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
                if path.startswith('/api/') or path == '/' or message['status'] >= 400:
                    headers['Cache-Control'] = 'no-store'
                elif path.startswith('/assets/'):
                    headers['Cache-Control'] = 'public, max-age=31536000, immutable' if path.startswith(self.asset_prefix + '/') else 'no-store'
            await send(message)
        async def reject(status, detail):
            body = json.dumps({'detail':detail}).encode()
            headers = [(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]
            if scope.get('http_version','1.1') in ('1.0','1.1'): headers.append((b'connection',b'close'))
            if status in (429,503): headers.append((b'retry-after',b'15'))
            await secured_send({'type':'http.response.start','status':status,'headers':headers})
            await secured_send({'type':'http.response.body','body':body})
        headers = scope.get('headers', [])
        if sum(len(k)+len(v) for k,v in headers) > 16384 or len(path) > 2048 or len(scope.get('query_string',b'')) > 2048:
            return await reject(431,'Request headers or URL exceed the limit')
        hosts = [v for k,v in headers if k.lower() == b'host']
        if len(hosts) != 1 or not valid_host(hosts[0], self.allowed_hosts):
            return await reject(400,'Invalid Host header')
        peer = (scope.get('client') or ('unknown',0))[0]
        mul = self.policy.rate_multiplier
        if not self.buckets.allow(('client',peer),120*mul,40) or not self.globals.allow(('global',),600*mul,120):
            return await reject(429,'Request rate limit reached; retry later')
        admin = (method in ('PUT','DELETE') and path.startswith('/api/v1/catalog/')) or (method == 'POST' and path == IMPORT)
        if admin:
            supplied = [v for k,v in headers if k.lower() == b'x-admin-token']
            if len(supplied) != 1 or not valid_token(self.token, supplied[0]):
                return await reject(403,'Admin token required; catalogue is read-only without ADMIN_TOKEN')
        expensive = method == 'POST' and path in HEAVY
        if expensive:
            quota = 6 if path == PDF else 4
            if not self.buckets.allow(('heavy',peer,path),quota*mul,3) or not self.globals.allow(('heavy-global',),30*mul,6):
                return await reject(429,'Operation rate limit reached; retry later')
        if self.active >= self.policy.connections or (expensive and self.heavy):
            return await reject(503,'Service busy; retry shortly')
        self.active += 1
        if expensive: self.heavy += 1
        try:
            cap = self.policy.library_body if path in (VALIDATE,IMPORT) else self.policy.report_body if path == PDF else self.policy.general_body
            lengths = [v for k,v in headers if k.lower() == b'content-length']
            if len(lengths) > 1 or (lengths and not re.fullmatch(rb'[0-9]{1,12}', lengths[0])):
                return await reject(400,'Invalid Content-Length')
            if lengths and int(lengths[0]) > cap:
                return await reject(413,'Request body exceeds the route size limit')
            if method in ('POST','PUT') and (path in HEAVY or path.startswith('/api/v1/catalog/')):
                types = [v.split(b';',1)[0].strip().lower() for k,v in headers if k.lower() == b'content-type']
                if len(types) != 1 or not (types[0] == b'application/json' or (types[0].startswith(b'application/') and types[0].endswith(b'+json'))):
                    return await reject(415,'JSON Content-Type is required')
            if any(k.lower() == b'content-encoding' and v.lower() != b'identity' for k,v in headers):
                return await reject(415,'Compressed request bodies are not supported')
            body = bytearray()
            try:
                async with asyncio.timeout(self.policy.body_timeout):
                    while True:
                        chunk = await receive()
                        if chunk['type'] == 'http.disconnect': return
                        data = chunk.get('body',b'')
                        if len(body) + len(data) > cap:
                            return await reject(413,'Request body exceeds the route size limit')
                        body.extend(data)
                        if not chunk.get('more_body',False): break
            except TimeoutError:
                return await reject(408,'Request body read timed out')
            if lengths and int(lengths[0]) != len(body):
                return await reject(400,'Request body length does not match Content-Length')
            delivered = False
            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()
            await self.app(scope, buffered_receive, secured_send)
        except Exception:
            log.exception('Request failed')
            if not started: await reject(500,'Request could not be completed')
            else: raise
        finally:
            self.active -= 1
            if expensive: self.heavy -= 1
