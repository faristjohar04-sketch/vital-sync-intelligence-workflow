"""Shared Google OAuth helper for Sheets + Gmail access.

Caches a user token at token.json after the first interactive consent flow.
credentials.json (OAuth client secret from Google Cloud Console) must exist
at the project root before the first run.
"""

import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
]

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"


def _interactive_reauth() -> Credentials:
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_PATH}. "
            "Download an OAuth client (Desktop app) from Google Cloud "
            "Console with the Sheets, Gmail, and Drive APIs enabled, and "
            "place it at the project root."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    return flow.run_local_server(port=0)


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                # Refresh tokens for OAuth clients in Google's "Testing"
                # publishing status expire after 7 days regardless of use —
                # this is the most common cause here. Move the OAuth consent
                # screen to "In production" (Google Cloud Console > OAuth
                # consent screen > Audience > Publish app) to stop this from
                # recurring; unattended/scheduled runs cannot complete the
                # interactive browser flow below on their own.
                print(
                    f"Stored Google token could not be refreshed ({e}). "
                    "Falling back to interactive re-authentication — this "
                    "requires a browser and will NOT work from an unattended "
                    "scheduled run. If this keeps happening every ~7 days, "
                    "move the OAuth consent screen to 'In production' status.",
                    file=sys.stderr,
                )
                creds = _interactive_reauth()
        else:
            creds = _interactive_reauth()
        TOKEN_PATH.write_text(creds.to_json())

    return creds
