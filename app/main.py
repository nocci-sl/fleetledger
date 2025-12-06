import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db, get_session
from .models import Server, User
from .utils import (
    encrypt_secret,
    decrypt_secret,
    can_encrypt,
    ensure_csrf_token,
    validate_csrf,
    parse_decimal,
    parse_ram_mb,
    parse_storage_gb,
)
from jinja2 import pass_context

from .i18n import AVAILABLE_LANGUAGES, resolve_locale, translate
from .auth import (
    hash_password,
    verify_password,
    get_current_user,
    require_current_user,
    require_admin,
)

app = FastAPI(title="FleetLedger")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["languages"] = AVAILABLE_LANGUAGES

# Session middleware (server-side session based on signed cookie)
SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET or SESSION_SECRET.startswith("CHANGE_ME"):
    raise RuntimeError(
        "SESSION_SECRET environment variable must be set to a strong random value."
    )

SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") != "0"
ALLOW_SELF_REGISTRATION = os.getenv("ALLOW_SELF_REGISTRATION", "0") == "1"


@app.middleware("http")
async def add_locale_to_request(request: Request, call_next):
    request.state.locale = resolve_locale(request)
    response = await call_next(request)
    return response


# Session middleware (server-side session based on signed cookie)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
    session_cookie="fleetledger_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
)


@pass_context
def _t(ctx, key: str, **kwargs) -> str:
    request = ctx.get("request")
    locale = getattr(request.state, "locale", "de") if request else "de"
    return translate(key, locale, **kwargs)


templates.env.globals["t"] = _t


@app.on_event("startup")
def on_startup() -> None:
    """Initialize database on startup."""
    init_db()


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    """Serve the PWA manifest."""
    return FileResponse(
        "app/static/manifest.webmanifest", media_type="application/manifest+json"
    )


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """Serve the service worker from root scope."""
    return FileResponse(
        "app/static/service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/lang/{code}", include_in_schema=False)
def switch_language(code: str, request: Request):
    """Persist preferred language in session and redirect back."""
    code = code.lower()
    if code not in AVAILABLE_LANGUAGES:
        return RedirectResponse("/", status_code=303)
    request.session["lang"] = code
    referer = request.headers.get("referer") or "/"
    return RedirectResponse(referer, status_code=303)


# ------------- Auth: Register / Login / Logout -------------


@app.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Render the registration form.

    If at least one user already exists, only admins may register new users.
    """
    user_count = len(session.exec(select(User)).all())
    if (
        user_count > 0
        and not ALLOW_SELF_REGISTRATION
        and (not current_user or not current_user.is_admin)
    ):
        return RedirectResponse("/", status_code=303)

    csrf_token = ensure_csrf_token(request)

    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "error": None,
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Handle registration submissions.

    - First user becomes admin automatically.
    - Later users can only be created by admins.
    """
    if not validate_csrf(request, csrf_token):
        token = ensure_csrf_token(request)
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Ungültiger Sicherheits-Token. Bitte erneut versuchen.",
                "current_user": current_user,
                "csrf_token": token,
            },
            status_code=400,
        )

    user_count = len(session.exec(select(User)).all())
    if (
        user_count > 0
        and not ALLOW_SELF_REGISTRATION
        and (not current_user or not current_user.is_admin)
    ):
        return RedirectResponse("/", status_code=303)

    error = None
    if password != password_confirm:
        error = "Passwords do not match."
    else:
        existing = session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing:
            error = "Username is already taken."

    csrf_token = ensure_csrf_token(request)

    if error:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": error,
                "current_user": current_user,
                "csrf_token": csrf_token,
            },
            status_code=400,
        )

    user = User(
        username=username,
        email=email or None,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=(user_count == 0),  # first user is admin
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Auto-login after registration
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user),
):
    """Render the login form."""
    if current_user:
        return RedirectResponse("/", status_code=303)
    csrf_token = ensure_csrf_token(request)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
):
    """Handle login submissions."""
    if not validate_csrf(request, csrf_token):
        token = ensure_csrf_token(request)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Ungültiger Sicherheits-Token. Bitte erneut versuchen.",
                "current_user": None,
                "csrf_token": token,
            },
            status_code=400,
        )

    user = session.exec(select(User).where(User.username == username)).first()
    error = None
    if not user or not verify_password(password, user.password_hash):
        error = "Invalid username or password."
    elif not user.is_active:
        error = "User is deactivated."

    csrf_token = ensure_csrf_token(request)

    if error:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": error,
                "current_user": None,
                "csrf_token": csrf_token,
            },
            status_code=400,
        )

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    """Log out the current user and clear the session."""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ------------- Admin: User management -------------


@app.get("/users", response_class=HTMLResponse)
def list_users(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """List all users (admin only)."""
    users = session.exec(select(User).order_by(User.username)).all()
    csrf_token = ensure_csrf_token(request)
    return templates.TemplateResponse(
        "users_list.html",
        {
            "request": request,
            "users": users,
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.post("/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Toggle a user's active state (admin only).

    An admin cannot deactivate themselves to avoid lockout.
    """
    if not validate_csrf(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token."
        )

    user = session.get(User, user_id)
    if not user:
        return RedirectResponse("/users", status_code=303)

    if user.id == current_user.id:
        return RedirectResponse("/users", status_code=303)

    user.is_active = not user.is_active
    session.add(user)
    session.commit()
    return RedirectResponse("/users", status_code=303)


# ------------- Admin: Global dashboard -------------


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Global admin dashboard aggregating all non-archived servers across all users.
    """
    servers = session.exec(
        select(Server).where(Server.archived == False)
    ).all()
    users = session.exec(select(User)).all()

    total_servers = len(servers)
    total_users = len(users)
    expiring_soon = sum(1 for s in servers if s.is_expiring_soon)
    expired = sum(1 for s in servers if s.is_expired)

    monthly_total = 0.0
    currencies = set()
    for s in servers:
        if not s.price:
            continue
        if s.currency:
            currencies.add(s.currency)
        if s.billing_period == "yearly":
            monthly_total += s.price / 12.0
        else:
            monthly_total += s.price

    monthly_currency = None
    if len(currencies) == 1:
        monthly_currency = next(iter(currencies))

    # Provider-level stats
    provider_stats = {}
    for s in servers:
        provider = s.provider or "Unknown"
        if provider not in provider_stats:
            provider_stats[provider] = {
                "count": 0,
                "monthly_total": 0.0,
                "expiring_soon": 0,
                "expired": 0,
                "currency_set": set(),
            }
        ps = provider_stats[provider]
        ps["count"] += 1
        if s.price:
            if s.currency:
                ps["currency_set"].add(s.currency)
            if s.billing_period == "yearly":
                ps["monthly_total"] += s.price / 12.0
            else:
                ps["monthly_total"] += s.price
        if s.is_expiring_soon:
            ps["expiring_soon"] += 1
        if s.is_expired:
            ps["expired"] += 1

    # Contracts expiring soon and expired, for small lists
    expiring_soon_list = sorted(
        [s for s in servers if s.is_expiring_soon],
        key=lambda s: s.contract_end or datetime.max.date(),
    )
    expired_list = sorted(
        [s for s in servers if s.is_expired],
        key=lambda s: s.contract_end or datetime.min.date(),
        reverse=True,
    )

    stats = {
        "total_servers": total_servers,
        "total_users": total_users,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "monthly_total": monthly_total,
        "monthly_currency": monthly_currency,
        "mixed_currencies": len(currencies) > 1,
    }

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "stats": stats,
            "provider_stats": provider_stats,
            "expiring_soon_list": expiring_soon_list,
            "expired_list": expired_list,
        },
    )


# ------------- Server views (CRUD, per user) -------------


@app.get("/", response_class=HTMLResponse)
def list_servers(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """
    List all non-archived servers owned by the current user.
    Additionally compute some summary stats for the dashboard.
    """
    servers = session.exec(
        select(Server)
        .where(Server.archived == False)
        .where(Server.owner_id == current_user.id)
        .order_by(Server.provider, Server.name)
    ).all()

    # --- Dashboard stats ---
    total_servers = len(servers)
    expiring_soon = sum(1 for s in servers if s.is_expiring_soon)
    expired = sum(1 for s in servers if s.is_expired)

    # Approximate total monthly cost
    monthly_total = 0.0
    currencies = set()
    for s in servers:
        if not s.price:
            continue
        if s.currency:
            currencies.add(s.currency)
        if s.billing_period == "yearly":
            monthly_total += s.price / 12.0
        else:
            # treat "monthly" and "other" as monthly for the purpose of the overview
            monthly_total += s.price

    monthly_currency = None
    if len(currencies) == 1:
        monthly_currency = next(iter(currencies))

    stats = {
        "total_servers": total_servers,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "monthly_total": monthly_total,
        "monthly_currency": monthly_currency,
        "mixed_currencies": len(currencies) > 1,
    }

    return templates.TemplateResponse(
        "servers_list.html",
        {
            "request": request,
            "servers": servers,
            "can_encrypt": can_encrypt(),
            "current_user": current_user,
            "stats": stats,
        },
    )


@app.get("/servers/new", response_class=HTMLResponse)
def new_server_form(
    request: Request,
    current_user: User = Depends(require_current_user),
):
    """Render a blank form for creating a new server."""
    csrf_token = ensure_csrf_token(request)
    return templates.TemplateResponse(
        "server_form.html",
        {
            "request": request,
            "server": None,
            "can_encrypt": can_encrypt(),
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.post("/servers/new")
def create_server(
    request: Request,
    name: str = Form(...),
    provider: str = Form(...),
    hostname: str = Form(""),
    type: str = Form("vps"),
    location: str = Form(""),
    ipv4: str = Form(""),
    ipv6: str = Form(""),
    billing_period: str = Form("monthly"),
    price: str = Form("0"),
    currency: str = Form("EUR"),
    contract_start: Optional[str] = Form(None),
    contract_end: Optional[str] = Form(None),
    cpu_model: str = Form(""),
    cpu_cores: int = Form(0),
    ram_mb: str = Form(""),
    storage_gb: str = Form(""),
    storage_type: str = Form(""),
    tags: str = Form(""),
    mgmt_url: str = Form(""),
    mgmt_user: str = Form(""),
    mgmt_password: str = Form(""),
    ssh_user: str = Form(""),
    ssh_key_hint: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """Create a new server entry for the current user."""
    if not validate_csrf(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token."
        )

    c_start = (
        datetime.fromisoformat(contract_start).date() if contract_start else None
    )
    c_end = datetime.fromisoformat(contract_end).date() if contract_end else None

    parsed_price = parse_decimal(price) or 0.0
    parsed_ram = parse_ram_mb(ram_mb)
    parsed_storage = parse_storage_gb(storage_gb)

    enc_pwd = encrypt_secret(mgmt_password) if mgmt_password else None

    # Only allow http:// or https:// URLs to avoid javascript: schemes etc.
    mgmt_url_clean = mgmt_url.strip()
    if mgmt_url_clean and not (
        mgmt_url_clean.lower().startswith("http://")
        or mgmt_url_clean.lower().startswith("https://")
    ):
        mgmt_url_clean = ""

    server = Server(
        owner_id=current_user.id,
        name=name,
        provider=provider,
        hostname=hostname or None,
        type=type,
        location=location or None,
        ipv4=ipv4 or None,
        ipv6=ipv6 or None,
        billing_period=billing_period,
        price=parsed_price,
        currency=currency,
        contract_start=c_start,
        contract_end=c_end,
        cpu_model=cpu_model or None,
        cpu_cores=cpu_cores or None,
        ram_mb=parsed_ram,
        storage_gb=parsed_storage,
        storage_type=storage_type or None,
        tags=tags or None,
        mgmt_url=mgmt_url_clean or None,
        mgmt_user=mgmt_user or None,
        mgmt_password_encrypted=enc_pwd,
        ssh_user=ssh_user or None,
        ssh_key_hint=ssh_key_hint or None,
        notes=notes or None,
        updated_at=datetime.utcnow(),
    )
    session.add(server)
    session.commit()
    session.refresh(server)
    return RedirectResponse(url="/", status_code=303)


@app.get("/servers/archived", response_class=HTMLResponse)
def archived_servers(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """List archived servers for the current user."""
    servers = session.exec(
        select(Server)
        .where(Server.archived == True)
        .where(Server.owner_id == current_user.id)
        .order_by(Server.provider, Server.name)
    ).all()

    csrf_token = ensure_csrf_token(request)

    return templates.TemplateResponse(
        "servers_archived.html",
        {
            "request": request,
            "servers": servers,
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.get("/servers/{server_id}", response_class=HTMLResponse)
def server_detail(
    server_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """Show details for a single server."""
    server = session.get(Server, server_id)
    if not server or server.owner_id != current_user.id:
        return RedirectResponse("/", status_code=303)

    decrypted_pwd = (
        decrypt_secret(server.mgmt_password_encrypted)
        if server.mgmt_password_encrypted
        else None
    )
    csrf_token = ensure_csrf_token(request)

    return templates.TemplateResponse(
        "server_detail.html",
        {
            "request": request,
            "server": server,
            "mgmt_password": decrypted_pwd,
            "can_encrypt": can_encrypt(),
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.get("/servers/{server_id}/edit", response_class=HTMLResponse)
def edit_server_form(
    server_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """Render a pre-filled form for editing an existing server."""
    server = session.get(Server, server_id)
    if not server or server.owner_id != current_user.id:
        return RedirectResponse("/", status_code=303)

    csrf_token = ensure_csrf_token(request)

    return templates.TemplateResponse(
        "server_form.html",
        {
            "request": request,
            "server": server,
            "can_encrypt": can_encrypt(),
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@app.post("/servers/{server_id}/edit")
def update_server(
    server_id: int,
    request: Request,
    name: str = Form(...),
    provider: str = Form(...),
    hostname: str = Form(""),
    type: str = Form("vps"),
    location: str = Form(""),
    ipv4: str = Form(""),
    ipv6: str = Form(""),
    billing_period: str = Form("monthly"),
    price: str = Form("0"),
    currency: str = Form("EUR"),
    contract_start: Optional[str] = Form(None),
    contract_end: Optional[str] = Form(None),
    cpu_model: str = Form(""),
    cpu_cores: int = Form(0),
    ram_mb: str = Form(""),
    storage_gb: str = Form(""),
    storage_type: str = Form(""),
    tags: str = Form(""),
    mgmt_url: str = Form(""),
    mgmt_user: str = Form(""),
    mgmt_password: str = Form(""),
    ssh_user: str = Form(""),
    ssh_key_hint: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """Update an existing server entry (only owner)."""
    server = session.get(Server, server_id)
    if not server or server.owner_id != current_user.id:
        return RedirectResponse("/", status_code=303)

    if not validate_csrf(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token."
        )

    c_start = (
        datetime.fromisoformat(contract_start).date() if contract_start else None
    )
    c_end = datetime.fromisoformat(contract_end).date() if contract_end else None

    # Only update mgmt password if a non-empty value was submitted.
    if mgmt_password:
        enc_pwd = encrypt_secret(mgmt_password)
        server.mgmt_password_encrypted = enc_pwd

    mgmt_url_clean = mgmt_url.strip()
    if mgmt_url_clean and not (
        mgmt_url_clean.lower().startswith("http://")
        or mgmt_url_clean.lower().startswith("https://")
    ):
        mgmt_url_clean = ""

    server.name = name
    server.provider = provider
    server.hostname = hostname or None
    server.type = type
    server.location = location or None
    server.ipv4 = ipv4 or None
    server.ipv6 = ipv6 or None
    server.billing_period = billing_period
    parsed_price = parse_decimal(price)
    server.price = parsed_price or 0.0
    server.currency = currency
    server.contract_start = c_start
    server.contract_end = c_end
    server.cpu_model = cpu_model or None
    server.cpu_cores = cpu_cores or None
    server.ram_mb = parse_ram_mb(ram_mb)
    server.storage_gb = parse_storage_gb(storage_gb)
    server.storage_type = storage_type or None
    server.tags = tags or None
    server.mgmt_url = mgmt_url_clean or None
    server.mgmt_user = mgmt_user or None
    server.ssh_user = ssh_user or None
    server.ssh_key_hint = ssh_key_hint or None
    server.notes = notes or None
    server.updated_at = datetime.utcnow()

    session.add(server)
    session.commit()
    return RedirectResponse(f"/servers/{server_id}", status_code=303)


@app.post("/servers/{server_id}/archive")
def archive_server(
    server_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """
    Soft-delete (archive) a server.

    The record is kept but not shown in the main list.
    """
    if not validate_csrf(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token."
        )

    server = session.get(Server, server_id)
    if not server or server.owner_id != current_user.id:
        return RedirectResponse("/", status_code=303)

    server.archived = True
    server.updated_at = datetime.utcnow()
    session.add(server)
    session.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/servers/{server_id}/unarchive")
def unarchive_server(
    server_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """Restore an archived server."""
    if not validate_csrf(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token."
        )

    server = session.get(Server, server_id)
    if not server or server.owner_id != current_user.id:
        return RedirectResponse("/", status_code=303)

    server.archived = False
    server.updated_at = datetime.utcnow()
    session.add(server)
    session.commit()
    return RedirectResponse("/servers/archived", status_code=303)


# ------------- Per-user map view -------------


@app.get("/map", response_class=HTMLResponse)
def server_map(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_current_user),
):
    """
    Show a per-user map view with all non-archived servers.

    Coordinates are not stored in the database. Instead, the frontend derives
    approximate positions from the location string (city/datacenter name)
    using a built-in city map and a deterministic fallback.
    """
    servers = session.exec(
        select(Server)
        .where(Server.archived == False)
        .where(Server.owner_id == current_user.id)
        .order_by(Server.provider, Server.name)
    ).all()

    return templates.TemplateResponse(
        "servers_map.html",
        {
            "request": request,
            "servers": servers,
            "current_user": current_user,
        },
    )
