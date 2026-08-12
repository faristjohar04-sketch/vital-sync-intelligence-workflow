"""Send an email via Gmail SMTP + an App Password.

This is a DELIBERATE second email path, not a violation of "don't build a
second email integration" — it exists because it runs in a different place
than tools/gmail_send.py:

  - gmail_send.py uses OAuth (credentials.json/token.json) — works great
    locally where those files exist, but a cloud-scheduled routine has no
    access to this machine's filesystem, so it can never see them.
  - gmail_smtp_send.py uses an App Password via plain SMTP — no local
    OAuth files needed, only two environment variables, so it's the one
    the cloud weekly-intelligence routine uses to send the report.

Local interactive runs should keep using gmail_send.py. Use this one only
from the cloud routine (or anywhere else without access to the OAuth
token files).

Required environment variables:
    GMAIL_SMTP_ADDRESS       — the sending Gmail address
    GMAIL_SMTP_APP_PASSWORD  — a 16-character App Password for that address
                                (myaccount.google.com/apppasswords, requires
                                2-Step Verification enabled)

Usage:
    python tools/gmail_smtp_send.py --to someone@example.com --subject "Hi" --body "Hello"
    python tools/gmail_smtp_send.py --to someone@example.com --subject "Report" --body "See attached" --attach path/to/file.pdf
"""

import argparse
import mimetypes
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(to: str, subject: str, body_text: str, attachments=None):
    """attachments: optional list of file paths to attach (e.g. a weekly PDF report)."""
    address = os.environ.get("GMAIL_SMTP_ADDRESS")
    app_password = os.environ.get("GMAIL_SMTP_APP_PASSWORD")
    if not address or not app_password:
        raise RuntimeError(
            "GMAIL_SMTP_ADDRESS and GMAIL_SMTP_APP_PASSWORD must be set in the "
            "environment (routine environment secrets in the cloud; .env locally)."
        )

    if attachments:
        message = MIMEMultipart()
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

    message["From"] = address
    message["To"] = to
    message["Subject"] = subject

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(address, app_password)
        server.sendmail(address, [to], message.as_string())

    return {"to": to, "subject": subject, "sent_via": "smtp"}


def _cli():
    parser = argparse.ArgumentParser(description="Send an email via Gmail SMTP + App Password")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--attach", action="append", default=None,
                         help="Path to a file to attach; repeatable for multiple attachments.")
    args = parser.parse_args()
    result = send_email(args.to, args.subject, args.body, attachments=args.attach)
    print(f"Sent via SMTP to {result['to']}.")


if __name__ == "__main__":
    _cli()
