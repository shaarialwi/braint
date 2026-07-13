"""
Google SSO (OAuth2 / OpenID Connect) for a Google Workspace domain.

Flow:
  1. GET /auth/login          -> redirects user to Google's consent screen
  2. Google redirects back to /auth/callback with a code
  3. We exchange the code for tokens, verify the ID token, and check the
     Workspace domain ("hd" claim) matches ALLOWED_WORKSPACE_DOMAIN
  4. We store the user + tokens in a signed session cookie

Requires a project in Google Cloud Console with the OAuth consent screen
configured as "Internal" (restricts sign-in to your Workspace org) or
"External" with domain verification, plus these scopes enabled:
  openid, email, profile,
  https://www.googleapis.com/auth/drive.readonly,
  https://www.googleapis.com/auth/gmail.readonly,
  https://www.googleapis.com/auth/documents.readonly,
  https://www.googleapis.com/auth/spreadsheets.readonly,
  https://www.googleapis.com/auth/presentations.readonly,
  https://www.googleapis.com/auth/calendar.readonly
"""
import os
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REDIRECT_URI = os.environ["GOOGLE_REDIRECT_URI"]
ALLOWED_WORKSPACE_DOMAIN = os.environ.get("ALLOWED_WORKSPACE_DOMAIN")

SCOPES = " ".join([
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": SCOPES},
)


async def login(request: Request):
    """Redirect to Google's OAuth consent screen."""
    # hd=... hints Google to show only accounts from this Workspace domain
    return await oauth.google.authorize_redirect(
        request, GOOGLE_REDIRECT_URI, hd=ALLOWED_WORKSPACE_DOMAIN
    )


async def callback(request: Request):
    """Handle Google's redirect back, verify domain, store session."""
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    email = userinfo.get("email", "")
    hd = userinfo.get("hd")  # Workspace domain claim on the ID token

    if ALLOWED_WORKSPACE_DOMAIN and hd != ALLOWED_WORKSPACE_DOMAIN:
        return RedirectResponse(url="/auth/denied")

    # Persist only what you need; access_token/refresh_token let you call
    # Drive/Gmail/Docs/Sheets/Calendar APIs on the user's behalf.
    request.session["user"] = {
        "email": email,
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
        "hd": hd,
    }
    request.session["access_token"] = token.get("access_token")
    request.session["refresh_token"] = token.get("refresh_token")

    return RedirectResponse(url="/")


def current_user(request: Request):
    return request.session.get("user")


def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
