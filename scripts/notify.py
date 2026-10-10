#!/usr/bin/env python3
"""Send a plain-text status email.

Usage: python scripts/notify.py "Subject" "Body"
Reads settings from environment variables (set in the GitHub workflow):
  NOTIFY_EMAIL   recipient (a repository *variable*; change it there to switch addresses)
  SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD   (repository *secrets*)
If any are missing it prints a notice and exits 0, so it never breaks a deploy.
"""
import os
import smtplib
import sys
from email.message import EmailMessage

subject, body = (sys.argv[1:3] + ["", ""])[:2]
env = {k: os.environ.get(k, "").strip() for k in
       ("NOTIFY_EMAIL", "SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD")}
missing = [k for k, v in env.items() if not v]
if missing:
    print(f"Notification skipped, not configured yet: {', '.join(missing)}")
    sys.exit(0)

msg = EmailMessage()
msg["Subject"] = f"[Truvector site] {subject}"
msg["From"] = env["SMTP_USERNAME"]
msg["To"] = env["NOTIFY_EMAIL"]
msg.set_content(body)
try:
    with smtplib.SMTP(env["SMTP_SERVER"], int(env["SMTP_PORT"]), timeout=30) as s:
        s.starttls()
        s.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
        s.send_message(msg)
    print("Notification sent.")
except Exception as e:  # never fail the deploy because email failed
    print(f"Notification failed: {e}")
