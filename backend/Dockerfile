FROM python:3.13-slim AS base

RUN groupadd --gid 10001 skjald \
 && useradd --uid 10001 --gid skjald --no-create-home --shell /usr/sbin/nologin skjald

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown skjald:skjald /data

USER skjald
EXPOSE 8000

# Trust X-Forwarded-For from any peer: the app port is published to nobody but Caddy
# on the internal network, and Caddy replaces the header for untrusted clients.
# app.setup prints a fresh setup token to the log while setup is pending.
CMD ["sh", "-c", "python -m app.migrate && python -m app.setup && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
