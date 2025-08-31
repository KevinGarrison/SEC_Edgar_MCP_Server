from google.auth.transport import requests as grequests
from google.oauth2 import id_token
from dotenv import load_dotenv
import cachetools
import os

load_dotenv() 

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

_req = grequests.Request()
_cache = cachetools.TTLCache(maxsize=1, ttl=3600)

def verify_google_id_token(id_tok: str) -> dict:
    """
    Verifies a Google ID token and enforces audience/issuer/email_verified.
    Returns claims dict on success, raises on failure.
    """
    claims = id_token.verify_oauth2_token(id_tok, _req, GOOGLE_CLIENT_ID)
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("Invalid issuer")
    if not claims.get("email_verified", False):
        raise ValueError("Email not verified")
    return claims