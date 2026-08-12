"""Send an email via the Gmail API using the authenticated OAuth account.

Runnable directly for ad hoc sends:

    python tools/gmail_send.py --to someone@example.com --subject "Hi" --body "Hello"
    python tools/gmail_send.py --to someone@example.com --subject "Report" --body "See attached" --attach path/to/file.pdf
"""

import argparse
import base64
import mimetypes
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google_auth import get_credentials
from googleapiclient.discovery import build


def send_email(to: str, subject: str, body_text: str, attachments=None):
    """attachments: optional list of file paths to attach (e.g. a weekly PDF report)."""
    service = build("gmail", "v1", credentials=get_credentials())

    if attachments:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body_text))
        for path in attachments:
            ctype, _ = mimetypes.guess_type(path)
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), _subtype=subtype)
            part.add_header(
                "Content-Disposition", "attachment", filename=os.path.basename(path)
            )
            message.attach(part)
    else:
        message = MIMEText(body_text)
        message["to"] = to
        message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def _cli():
    parser = argparse.ArgumentParser(description="Send an email via Gmail API")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--attach", action="append", default=None,
                         help="Path to a file to attach; repeatable for multiple attachments.")
    args = parser.parse_args()
    result = send_email(args.to, args.subject, args.body, attachments=args.attach)
    print(f"Sent. Message ID: {result.get('id')}")


if __name__ == "__main__":
    _cli()
