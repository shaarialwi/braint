"""
FastAPI entrypoint for the Workspace AI Brain backend.

Responsibilities:
  - Google SSO (see auth.py)
  - Session-protected API the frontend (the Workspace AI Brain.dc.html
    prototype, or its React/production rebuild) calls
  - A single /api/query endpoint that hands the request off to n8n,
    which does the actual source fan-out + Gemini call + vector lookup
    (see the workflow diagram in the design for the full step list)

Run locally:
  cp .env.example .env   # fill in real values
  pip install -r requirements.txt
  uvicorn main:app --reload
"""
import os
from dotenv import load_dotenv
load_dotenv()

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException
from starlette.middleware.sessions import SessionMiddleware

import auth

app = FastAPI(title="Workspace AI Brain API")
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])

N8N_BASE_URL = os.environ["N8N_BASE_URL"]
N8N_WEBHOOK_PATH = os.environ["N8N_WEBHOOK_PATH"]
N8N_API_KEY = os.environ.get("N8N_API_KEY")


def require_user(request: Request):
    user = auth.current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


# ---- Auth routes ----
@app.get("/auth/login")
async def login(request: Request):
    return await auth.login(request)


@app.get("/auth/callback")
async def callback(request: Request):
    return await auth.callback(request)


@app.get("/auth/logout")
async def logout_route(request: Request):
    return auth.logout(request)


@app.get("/auth/denied")
async def denied():
    return {"error": "This app is restricted to your Google Workspace organization."}


@app.get("/api/me")
async def me(user=Depends(require_user)):
    return user


# ---- Core query endpoint: hands off to n8n ----
@app.post("/api/query")
async def query(request: Request, user=Depends(require_user)):
    """
    Body: { "message": "Find all documents related to Project Nova" }

    Forwards the request + the caller's Google access token to n8n, which
    runs the full pipeline shown in the design's workflow diagram:
    understand intent -> route -> fan out to Drive/Gmail/Docs/Sheets/
    Slides/Calendar -> merge & embed -> vector search -> Gemini -> answer.
    """
    body = await request.json()
    message = body.get("message", "")
    access_token = request.session.get("access_token")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{N8N_BASE_URL}{N8N_WEBHOOK_PATH}",
            json={
                "message": message,
                "user_email": user["email"],
                "google_access_token": access_token,
            },
            headers={"Authorization": f"Bearer {N8N_API_KEY}"} if N8N_API_KEY else {},
        )
        resp.raise_for_status()
        return resp.json()


# ---- Simple source status, mirrors the "Sources" panel in the design ----
@app.get("/api/sources/status")
async def sources_status(user=Depends(require_user)):
    # Replace with real last-sync timestamps stored by your n8n indexing
    # workflows (e.g. in the same Postgres/pgvector database).
    return {
        "sources": [
            {"name": "Google Drive", "connected": True, "last_sync": None},
            {"name": "Gmail", "connected": True, "last_sync": None},
            {"name": "Google Docs", "connected": True, "last_sync": None},
            {"name": "Google Sheets", "connected": True, "last_sync": None},
            {"name": "Google Slides", "connected": True, "last_sync": None},
            {"name": "Google Calendar", "connected": True, "last_sync": None},
            {"name": "Gemini", "connected": True, "last_sync": None},
        ]
    }
