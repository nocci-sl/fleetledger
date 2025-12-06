# FleetLedger

FleetLedger is a small self-hosted web app to keep track of your rented servers:

- VPS, dedicated servers, storage boxes, managed services
- Provider, location, IPs, hardware
- Monthly / yearly pricing and contract dates
- Simple access info (management URLs, SSH user + key hint)
- Multi-user support with per-user data separation
- Admin user management (activate / deactivate users)
- Dark-mode-first UI with PWA support (installable as an app)
- Per-user **map view** for server locations
- Admin **global dashboard** for fleet-wide stats

> **Security note:** FleetLedger is *not* a full password manager.
> It is intentionally designed to store only **management password(s) optionally** and
> only **SSH key *names*** (no private keys).

---

## Features

- **Authentication & Users**
  - User registration + login (session cookie based)
  - First registered user becomes **admin**
  - Admin can view all users and activate/deactivate them
  - Deactivated users cannot log in and will be logged out automatically

- **Server Management**
  - Each user has their own list of servers (no cross-visibility)
  - Create / edit / archive (soft-delete) servers
  - Fields include:
    - General: name, hostname, type (VPS, dedicated, storage, managed, other), provider, location, tags
    - Network: IPv4, IPv6
    - Billing: price, currency, billing period (monthly/yearly/other), contract start/end
    - Hardware: CPU model, core count, RAM, storage size & type
    - Access: management URL, management user, management password (optional), SSH user, SSH key hint
    - Free-form notes
  - Contract badges:
    - **"abgelaufen"** (expired): contract end in the past
    - **"läuft bald aus"** (expiring soon): contract end within the next 30 days
    - Detail view also shows how many days until / since contract end

- **Per-user Dashboard & Map**
  - On `/`: small dashboard row showing:
    - number of active servers
    - estimated total monthly cost
    - how many contracts are expiring soon / already expired
  - On `/map`: Leaflet-based map showing all non-archived servers of the logged-in user
    - Marker position is derived from the `location` string (city/datacenter name)
    - Multiple servers per city are slightly offset so all markers remain clickable
    - Click on a marker → opens the server details page

- **Admin Global Dashboard**
  - On `/admin/dashboard` (admin only):
    - Global counts: users, servers, monthly cost, expiring soon, expired
    - Breakdown by provider (server count, monthly total, expiring soon, expired)
    - List of contracts expiring soon and already expired

- **Security**
  - Passwords hashed with **bcrypt** (`passlib[bcrypt]`)
  - Optional encryption for management passwords using **Fernet** (`cryptography`)
  - No private SSH keys are stored, only name/hint strings
  - Jinja2 auto-escaping enabled; no untrusted HTML is rendered with `|safe`
  - Management URLs are restricted to `http://` or `https://` (no `javascript:` links, etc.)

- **UI / UX**
  - TailwindCSS via CDN for quick styling
  - Dark mode is **enabled by default**
  - Theme preference stored in `localStorage` and toggleable via a small button
  - Responsive layout, works well on mobile
  - PWA manifest and service worker for a simple offline-friendly experience

---

## Quick Start (Docker)

### 0. Environment

Kopiere `.env-example` nach `.env` und setze mindestens ein starkes `SESSION_SECRET`. Für lokale HTTP-Tests kannst du `SESSION_COOKIE_SECURE=0` setzen, in Produktion sollte es `1` bleiben. Optional kannst du einen `ENCRYPTION_KEY` (Fernet) hinterlegen, um Management-Passwörter zu speichern.

### 1. Clone / copy the repository

```bash
git clone https://example.com/your/fleetledger.git
cd fleetledger
