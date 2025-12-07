# FleetLedger

Self-hosted overview for rented servers (VPS, dedicated, storage, managed). Multi-user, dark-mode first, PWA-ready.

## Features
- Server CRUD per user with soft delete/archiving
- Dashboard (costs, expiring contracts) and admin-wide overview
- Map view per user (Leaflet) based on location names
- Optional encrypted storage of management passwords (Fernet)
- Session auth with CSRF protection, admin role
- PWA: manifest, service worker, installable

## Stack
- FastAPI, SQLModel, Jinja2
- SQLite (default), Passlib (bcrypt), Cryptography (Fernet)
- Tailwind via CDN, Leaflet for maps
- Uvicorn as ASGI server

## Containers and Images
- Public repo: `https://github.com/nocci-sl/fleetledger`.
- Prebuilt image on GHCR: `ghcr.io/nocci-sl/fleetledger:latest` (plus commit-tagged `ghcr.io/nocci-sl/fleetledger:<git-sha>`).
  - Pull directly with `docker pull ghcr.io/nocci-sl/fleetledger:latest`.

## Quickstart with Docker Compose (prebuilt image)
Use the published GHCR image; no local build needed.
```bash
cp .env-example .env
# set SESSION_SECRET in .env to a strong random value

cat > docker-compose.override.yml <<'EOF'
services:
  fleetledger:
    image: ghcr.io/nocci-sl/fleetledger:latest
    environment:
      SESSION_SECRET: ${SESSION_SECRET:?set in .env}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-1}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-}
      ALLOW_SELF_REGISTRATION: ${ALLOW_SELF_REGISTRATION:-0}
    volumes:
      - ./data:/app/data
EOF

docker-compose up -d
```
SQLite will live on the host in `./data/fleetledger.db`.

## Quickstart with Docker (build locally)
```bash
cp .env-example .env
# set SESSION_SECRET in .env
docker build -t fleetledger:local .
mkdir -p data
docker run --rm -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data fleetledger:local
```

## Local development (without Docker)
Requirements: Python 3.12, virtualenv recommended.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env-example .env
export SESSION_SECRET="long_random_value"
export SESSION_COOKIE_SECURE=0  # only for local HTTP
uvicorn app.main:app --reload --port 8000
```

## Environment variables
- `SESSION_SECRET` (required): long random string for session signing.
- `SESSION_COOKIE_SECURE` (default `1`): set `0` only for local HTTP; keep `1` with HTTPS.
- `DATABASE_PATH` (default `/app/data/fleetledger.db`): SQLite file path; locally e.g. `./data/fleetledger.db`.
- `ENCRYPTION_KEY` (optional): Fernet key for encrypted management passwords. Leave empty to disable persistence of these passwords.
- `ALLOW_SELF_REGISTRATION` (default `0`): `1` allows new self-registrations even if an admin exists; `0` means only admin can create users.

## Security notes
- Always use a strong `SESSION_SECRET`; the container refuses to start with a placeholder.
- Run behind HTTPS (`SESSION_COOKIE_SECURE=1`).
- Only store management passwords if `ENCRYPTION_KEY` is set.
- CSRF protection is enabled for form POSTs; service worker caches assets with versioning.

## Data
- SQLite stores data in the file at `DATABASE_PATH`. In Docker, `./data/` on the host is mounted to `/app/data/` in the container.
- Backups: copy the SQLite file in `./data/` while the service is stopped.
