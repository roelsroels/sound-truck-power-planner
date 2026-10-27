"""Production-image smoke checks, requiring no development dependencies."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    with tempfile.TemporaryDirectory() as directory:
        env={**os.environ,'DB_PATH':str(Path(directory)/'test.sqlite3'),'ADMIN_TOKEN':'','ENABLE_API_DOCS':'false'}
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8080','--no-access-log'],env=env)
        def call(path,data=None,headers=None):
            request=Request('http://127.0.0.1:8080'+path,data=data,headers=headers or {})
            try:
                with urlopen(request,timeout=18) as response:return response.status,response.read()
            except HTTPError as response:return response.code,response.read()
        try:
            for _ in range(100):
                try:
                    if call('/api/health')[0]==200:break
                except URLError:pass
                time.sleep(.1)
            else:raise AssertionError('Server did not start')
            project=json.loads(call('/api/v1/example')[1]);equipment=json.loads(call('/api/v1/catalog')[1])
            raw=json.dumps({'project':project,'equipment':equipment}).encode()
            status,document=call('/api/v1/reports/engineering.pdf',raw,{'Content-Type':'application/json'})
            assert status==200 and document.startswith(b'%PDF'),(status,document[:200])
            pack=(Path(__file__).resolve().parent.parent/'web/library-template.json').read_bytes()
            assert call('/api/v3/library/validate',pack,{'Content-Type':'application/json'})[0]==200
            assert call('/api/v3/library/import',pack,{'Content-Type':'application/json'})[0]==403
            assert call('/api/v1/reports/engineering.pdf',b'x'*2_000_001,{'Content-Type':'application/json'})[0]==413
            assert call('/docs')[0]==404
            assert len(json.loads(call('/api/v3/library')[1])['products'])>=500
            print('Production image: isolated PDF/library work, body cap and authorization passed.')
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
