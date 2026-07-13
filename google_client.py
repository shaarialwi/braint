"""
Thin wrappers around the Google Workspace APIs used by the AI Brain.
Each function takes the user's OAuth access token (from the session,
see auth.py) and returns plain dicts ready to feed into the vector store
or straight back to the UI.

In production, wrap all of these in n8n HTTP Request nodes instead of
calling them directly from this service if you want retries, rate
limiting, and credential rotation handled by n8n (see the "Enterprise
Data Sources" step in the design's workflow diagram).
"""
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def _creds(access_token: str) -> Credentials:
    return Credentials(token=access_token)


def search_drive(access_token: str, query: str, page_size: int = 20):
    service = build("drive", "v3", credentials=_creds(access_token))
    results = service.files().list(
        q=f"fullText contains '{query}'",
        pageSize=page_size,
        fields="files(id,name,mimeType,webViewLink,modifiedTime,parents)",
    ).execute()
    return results.get("files", [])


def search_gmail(access_token: str, query: str, max_results: int = 20):
    service = build("gmail", "v1", credentials=_creds(access_token))
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    detailed = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        detailed.append({
            "id": msg["id"],
            "subject": headers.get("Subject"),
            "from": headers.get("From"),
            "date": headers.get("Date"),
            "snippet": msg.get("snippet"),
        })
    return detailed


def list_upcoming_events(access_token: str, max_results: int = 20):
    service = build("calendar", "v3", credentials=_creds(access_token))
    events = service.events().list(
        calendarId="primary", maxResults=max_results,
        singleEvents=True, orderBy="startTime",
    ).execute()
    return events.get("items", [])


def get_doc_text(access_token: str, document_id: str) -> str:
    service = build("docs", "v1", credentials=_creds(access_token))
    doc = service.documents().get(documentId=document_id).execute()
    text = []
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        for run in para.get("elements", []):
            text.append(run.get("textRun", {}).get("content", ""))
    return "".join(text)


def get_sheet_values(access_token: str, spreadsheet_id: str, range_: str = "A1:Z100"):
    service = build("sheets", "v4", credentials=_creds(access_token))
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range_
    ).execute()
    return result.get("values", [])
