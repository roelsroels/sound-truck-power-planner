FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f AS source-revision
WORKDIR /build
# Only HEAD and branch refs are allowed through .dockerignore; no Git config/history.
# .gitignore keeps this COPY valid for source archives that have no .git directory.
COPY .git* ./
COPY app/revision.py ./revision.py
RUN python revision.py /build /build/build_revision.json

FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/planner.sqlite3 FORWARDED_ALLOW_IPS=127.0.0.1
WORKDIR /opt/planner
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt && \
    groupadd -g 10001 planner && useradd --no-log-init -g planner -u 10001 -s /usr/sbin/nologin planner
COPY app ./app
COPY web ./web
COPY --from=source-revision /build/build_revision.json ./app/build_revision.json
RUN mkdir /data && chown planner:planner /data
USER planner
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=3)'
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers","--limit-concurrency","32","--backlog","64","--timeout-keep-alive","5","--timeout-graceful-shutdown","15","--no-server-header"]
