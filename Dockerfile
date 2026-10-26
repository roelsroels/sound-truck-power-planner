FROM python:3.12-slim AS source-revision
WORKDIR /build
# Only HEAD and branch refs are allowed through .dockerignore; no Git config/history.
# .gitignore keeps this COPY valid for source archives that have no .git directory.
COPY .git* ./
COPY app/revision.py ./revision.py
RUN python revision.py /build /build/build_revision.json

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/planner.sqlite3
WORKDIR /opt/planner
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd -g 10001 planner && useradd --no-log-init -g planner -u 10001 -s /usr/sbin/nologin planner
COPY --chown=planner:planner app ./app
COPY --chown=planner:planner web ./web
COPY --from=source-revision --chown=planner:planner /build/build_revision.json ./app/build_revision.json
RUN mkdir /data && chown planner:planner /data
USER planner
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=3)'
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","127.0.0.1"]
