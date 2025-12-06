# FleetLedger

Self-hosted Übersicht für gemietete Server (VPS, Dedizierte, Storage, Managed). Mehrnutzerfähig, Dark-Mode-first und PWA-ready.

## Features
- Server-CRUD pro Benutzer, Soft-Delete/Archiv
- Dashboard (Kosten, ablaufende Verträge) + Admin-Gesamtübersicht
- Map-Ansicht pro Nutzer auf Basis der Location-Namen (Leaflet)
- Optional verschlüsselte Speicherung von Management-Passwörtern (Fernet)
- Session-Auth mit CSRF-Schutz, Admin-Rolle
- PWA: Manifest, Service Worker, installierbar

## Stack
- FastAPI, SQLModel, Jinja2
- SQLite (Standard), Passlib (bcrypt), Cryptography (Fernet)
- Tailwind via CDN, Leaflet für Karte
- Uvicorn als ASGI-Server

## Schnellstart mit Docker
1. Repository klonen
   ```bash
   git clone https://example.com/your/fleetledger.git
   cd fleetledger
   ```
2. Umgebung setzen
   ```bash
   cp .env-example .env
   # SESSION_SECRET in .env auf einen starken, einzigartigen Wert setzen
   ```
3. Starten
   ```bash
   docker-compose up --build
   ```
   Die SQLite-DB liegt in `./data/` (Bind-Mount in den Container unter `/app/data/fleetledger.db`).

## Lokale Entwicklung (ohne Docker)
- Voraussetzungen: Python 3.12, virtualenv empfohlen.
- Setup:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  cp .env-example .env
  export SESSION_SECRET="ein_langer_random_wert"
  export SESSION_COOKIE_SECURE=0  # nur lokal ohne HTTPS
  uvicorn app.main:app --reload --port 8000
  ```

## Umgebungsvariablen
- `SESSION_SECRET` (erforderlich): Langer, zufälliger String für die Session-Signierung.
- `SESSION_COOKIE_SECURE` (default `1`): Auf `0` nur für lokale HTTP-Tests setzen, sonst `1` (HTTPS).
- `DATABASE_PATH` (default `/app/data/fleetledger.db` im Docker-Image): Pfad zur SQLite-Datei. Lokal z. B. `./data/fleetledger.db`.
- `ENCRYPTION_KEY` (optional): Fernet-Key für verschlüsselte Management-Passwörter. Leer lassen, wenn keine Speicherung gewünscht ist.
- `ALLOW_SELF_REGISTRATION` (default `0`): `1` erlaubt neue Selbst-Registrierungen auch wenn schon ein Admin existiert; `0` = nur Admin darf weitere User anlegen.

## Sicherheitshinweise
- Immer einen starken `SESSION_SECRET` verwenden; im Docker-Setup wird der Start verweigert, wenn ein Platzhalter genutzt wird.
- Produktiv hinter HTTPS betreiben (`SESSION_COOKIE_SECURE=1`).
- Management-Passwörter nur mit gesetztem `ENCRYPTION_KEY` speichern; ohne Key werden sie nicht persistiert.
- CSRF-Schutz ist aktiv für Form-POSTs; Browser-Service-Worker cached Assets versioniert.

## Datenhaltung
- SQLite speichert die Daten in einer Datei (`DATABASE_PATH`). In Docker wird `./data/` aus dem Host eingebunden.
- Backups: Einfach die SQLite-Datei in `./data/` sichern, während der Dienst gestoppt ist.
