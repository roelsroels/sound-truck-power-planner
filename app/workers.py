"""One disposable, memory/CPU/time-bounded process for expensive untrusted work."""
import asyncio
import json
import multiprocessing
import os
import sys
from threading import Lock
from fastapi import HTTPException

MAX_RESULT = 10_000_000


def json_result(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def execute(kind, payload, path):
    from pydantic import ValidationError
    from . import library
    from .models import ReportInput, InspectInput
    try:
        if kind == 'pdf':
            from .report import build_pdf
            body = ReportInput.model_validate_json(payload)
            return 200, build_pdf(body.project.model_dump(),[e.model_dump() for e in body.equipment]), 'application/pdf'
        if kind in ('validate','import'):
            pack = library.Pack.model_validate_json(payload)
            if kind == 'import':
                return 200, json_result(library.import_pack(path,pack)), 'application/json'
            return 200, pack.model_dump_json().encode(), 'application/json'
        if kind == 'inspect':
            from . import spec_lookup
            body = InspectInput.model_validate_json(payload)
            return 200, json_result(spec_lookup.inspect(body.url)), 'application/json'
        raise ValueError('Unknown operation')
    except ValidationError as exc:
        # Never reflect user values or a huge error list into the response.
        first = exc.errors(include_input=False,include_url=False)[0]
        return 422, json_result({'detail':'Invalid input at '+'.'.join(map(str,first['loc']))}), 'application/json'
    except (ValueError,TypeError,KeyError):
        return 422, json_result({'detail':'Invalid or unavailable input; check the data and source'}), 'application/json'


def packet(status,body,media):
    return str(status).encode('ascii') + (b'P' if media == 'application/pdf' else b'J') + body


def decode_result(value):
    if len(value)<4 or value[:3] not in (b'200',b'422',b'503') or value[3:4] not in (b'P',b'J'):
        raise ValueError('Invalid worker result')
    return int(value[:3]),value[4:],'application/pdf' if value[3:4] == b'P' else 'application/json'


def child(send, kind, payload, path, memory_mb):
    # No administration credential is needed for parsing or rendering.
    os.environ.pop('ADMIN_TOKEN',None)
    try:
        if sys.platform.startswith('linux'):
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024*1024,memory_mb*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(8,8))
        status, body, media = execute(kind,payload,path)
        if len(body)>MAX_RESULT: raise MemoryError()
        send.send_bytes(packet(status,body,media))
    except (MemoryError,OverflowError):
        send.send_bytes(packet(503,json_result({'detail':'Operation exceeded its resource budget'}),'application/json'))
    except Exception:
        send.send_bytes(packet(422,json_result({'detail':'Operation could not process the supplied data'}),'application/json'))
    finally:
        send.close()


class Worker:
    def __init__(self, timeout=12, memory_mb=192):
        self.timeout=timeout;self.memory_mb=memory_mb;self.lock=Lock()

    def _run(self,kind,payload,path):
        context=multiprocessing.get_context('spawn')
        receive,send=context.Pipe(duplex=False)
        process=context.Process(target=child,args=(send,kind,payload,path,self.memory_mb),daemon=True)
        try:
            process.start();send.close()
            if not receive.poll(self.timeout):
                raise HTTPException(status_code=503,detail='Operation timed out; retry later')
            try:
                return decode_result(receive.recv_bytes(maxlength=MAX_RESULT+4))
            except (EOFError,OSError,ValueError):
                raise HTTPException(status_code=503,detail='Operation exceeded its resource budget')
        finally:
            send.close();receive.close()
            if process.pid:
                if process.is_alive():process.terminate()
                process.join(1)
                if process.is_alive():process.kill();process.join(1)
                if not process.is_alive():process.close()

    async def run(self,kind,payload,path=None):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(status_code=503,detail='Service busy; retry shortly')
        def job():
            try:return self._run(kind,payload,path)
            finally:self.lock.release()
        # Shield cancellation: capacity remains reserved until the child exits.
        task=asyncio.create_task(asyncio.to_thread(job))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            raise
