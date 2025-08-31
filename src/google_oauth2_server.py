from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from authlib.integrations.starlette_client import OAuth
from starlette.templating import Jinja2Templates
from starlette.requests import Request
from fastmcp import FastMCP, Context
from typing import Literal, Optional
from datetime import datetime
from modules import utils
import sqlite3
import hashlib
import secrets
import hmac
import time
import os

templates = Jinja2Templates(directory="src/templates")

# -----------------------------------------------
# API Key mint/verify helpers (persisted in SQLite)
# -----------------------------------------------

API_KEY_PREFIX = "sk_mcp_"
API_KEY_HASH_SECRET = os.getenv("API_KEY_HASH_SECRET", default=None)
DB_PATH = "data/api_keys.db"


def _hash_api_key(raw: str) -> str:
    return hmac.new(API_KEY_HASH_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()

def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                hash TEXT PRIMARY KEY,
                service TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _db_connect():
    return sqlite3.connect(DB_PATH)


_init_db()


def create_api_key(service: str, ttl_days: int = 30) -> str:
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = _hash_api_key(raw)
    now = int(time.time())
    expires = now + ttl_days * 24 * 3600
    conn = _db_connect()
    try:
        conn.execute(
            "INSERT INTO api_keys (hash, service, created_at, expires_at, revoked) VALUES (?, ?, ?, ?, 0)",
            (key_hash, service, now, expires),
        )
        conn.commit()
    finally:
        conn.close()
    return raw


def lookup_api_key(raw: str) -> Optional[dict]:
    key_hash = _hash_api_key(raw)
    conn = _db_connect()
    try:
        cur = conn.execute(
            "SELECT service, created_at, expires_at, revoked FROM api_keys WHERE hash = ?",
            (key_hash,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    service, created_at, expires_at, revoked = row
    if revoked:
        return None
    if expires_at and time.time() > float(expires_at):
        return None
    return {
        "service": service,
        "created_at": created_at,
        "expires_at": expires_at,
        "revoked": bool(revoked),
    }


# --------------------------------------------------
# MCP + Starlette app setup
# --------------------------------------------------
FormType = Literal[
    "10-K", "10-Q", "8-K",
    "S-1", "S-3", "DEF 14A",
    "20-F", "6-K", "4",
    "13D", "13G",
]

instructions = """
This MCP server provides a search for the latest SEC filings from the EDGAR API.
"""

mcp = FastMCP('sec-edgar-mcp', instructions=instructions)
app = mcp.streamable_http_app()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", secrets.token_hex(32)),
    same_site="lax",
    https_only=True,           
    max_age=86400
)


oauth = OAuth()

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth.register(
    name='google',
    server_metadata_url=CONF_URL,
    client_id=os.getenv('GOOGLE_CLIENT_ID', default=None),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET', default=None),
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'consent select_account',
    }
)

# --------------------------------------------------
# Public routes for health and the Google login + key mint
# --------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health_check():
    return JSONResponse({"status": "healthy", "service": "mcp-server"})


@app.route('/', methods=["GET"])
async def homepage(request: Request):
    user = request.session.get('user')
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "user": None})
    return RedirectResponse('/keys')


@app.route('/login')
async def login(request):
    nonce = secrets.token_urlsafe(16)
    request.session['nonce'] = nonce
    redirect_uri = str(request.url_for('auth'))
    return await oauth.google.authorize_redirect(request, redirect_uri, nonce=nonce)


@app.route('/auth')
async def auth(request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo') or {}
    if not userinfo:
        request.session.clear()
        return HTMLResponse("Login succeeded but no userinfo returned.", status_code=400)
    request.session['user'] = {
        "sub": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }
    return RedirectResponse('/keys', status_code=303)


@app.route('/keys', methods=["GET"])
async def keys_page(request: Request):
    user = request.session.get('user')
    if not user:
        return RedirectResponse('/login')
    conn = _db_connect()
    try:
        cur = conn.execute(
            "SELECT hash, service, created_at, expires_at, revoked FROM api_keys ORDER BY created_at DESC"
        )
        rows = []
        for h, service, created_at, expires_at, revoked in cur.fetchall():
            rows.append({
                "hash": h,
                "service": service,
                "created_at": datetime.fromtimestamp(int(created_at)).isoformat(),
                "expires_at": datetime.fromtimestamp(int(expires_at)).isoformat(),
                "revoked": bool(revoked),
            })
    finally:
        conn.close()
    flash_key = request.session.pop('flash_api_key', None)
    return templates.TemplateResponse("keys.html", {"request": request, "user": user, "rows": rows, "flash_api_key": flash_key})


@app.route('/keys/create', methods=["POST"])
async def keys_create(request: Request):
    user = request.session.get('user')
    if not user:
        return RedirectResponse('/login')
    form = await request.form()
    label = (form.get('label') or 'default').strip()
    api_key = create_api_key(service=label)
    request.session['flash_api_key'] = api_key
    return RedirectResponse('/keys', status_code=303)


@app.route('/api/create-key')
async def create_key(request):
    user = request.session.get('user')
    if not user:
        return HTMLResponse("Please <a href='/login'>login</a> first.", status_code=401)
    api_key = create_api_key(service="default")
    request.session['flash_api_key'] = api_key
    return RedirectResponse('/keys', status_code=303)


@app.route('/keys/revoke', methods=["POST"])
async def keys_revoke(request: Request):
    user = request.session.get('user')
    if not user:
        return RedirectResponse('/login')
    form = await request.form()
    key_hash = form.get('hash')
    if key_hash:
        conn = _db_connect()
        try:
            conn.execute(
                "DELETE FROM api_keys WHERE hash = ?",
                (key_hash,),
            )
            conn.commit()
        finally:
            conn.close()
    return RedirectResponse('/keys', status_code=303)


@app.route('/logout')
async def logout(request):
    request.session.clear()
    return RedirectResponse(url='/')


# --------------------------------------------------
# API Key middleware for MCP tool calls
# --------------------------------------------------
class APIKeyAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path in {"/health", "/", "/login", "/auth", "/logout", "/api/create-key", "/keys", "/keys/revoke", "/keys/create"}:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else request.headers.get("x-api-key")
        if not token:
            return JSONResponse({"error": "missing access token"}, status_code=401)

        rec = lookup_api_key(token)
        if not rec:
            return JSONResponse({"error": "invalid or expired access token"}, status_code=401)

        request.state.user = {"service": rec["service"]}
        return await call_next(request)


app.add_middleware(APIKeyAuth)


# --------------------------------------------------
# MCP Tool (unchanged), with a small UA guard for EDGAR
# --------------------------------------------------
@mcp.tool("edgar-api-latest-filings")
async def company_filings(ctx: Context, company_ticker: str, form:FormType, cursor:int, user_agent:str):
    """
    Fetch the latest SEC filing for a given company and form type,
    returning the filing text in token-safe chunks.
    """
    ua = (user_agent or "").strip()
    if "@" not in ua:
        return {"error": "SEC EDGAR requires a User-Agent with a contact email (e.g., 'YourApp/1.0 (you@example.com)')"}, 400

    cik = await utils.company_cik_by_ticker(ctx, company_ticker, ua)
    context_1, context_2, context_3 = await utils.fetch_selected_company_details_and_filing_accessions(ctx, cik, ua)
    mapped_index = utils.get_latest_filings_index(context_3)
    sec_base_df = utils.create_base_df_for_sec_company_data(mapping_latest_docs=mapped_index, filings=context_3, cik=cik)
    latest_filings = await utils.fetch_all_filings(ctx=ctx, sec__base_df=sec_base_df, user_agent=ua)
    sec_base_df['filing_raw'] = latest_filings
    selected_form = sec_base_df[sec_base_df['form'] == form]
    if selected_form.empty:
        return {"error": f"No filing found for form '{form}' for ticker '{company_ticker}'."}, 404

    filing = selected_form.iloc[0]
    sec_context = dict()
    sec_context['company_cik'] = cik
    sec_context['filing_accession'] = filing['accession_number']
    sec_context['filing_report_date'] = filing['report_date']
    sec_context['filing_form'] = filing['form']
    sec_context['company_context_1'] = context_1
    sec_context['company_context_2'] = context_2
    sec_context['filing_filename'] = filing['docs']
    sec_filing = utils.preprocess_docs_content(filing['filing_raw']).document.export_to_markdown()
    chunks = utils.chunk_docs_content(sec_filing)
    sec_context['max_cursor'] = len(chunks) - 1

    if cursor < 0 or cursor > sec_context['max_cursor']:
        return {"error": f"cursor out of range. Valid range: 0..{sec_context['max_cursor']}"}, 400

    sec_context[f'filing_chunk_{cursor}'] = chunks[cursor]
    return sec_context


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app=app)
