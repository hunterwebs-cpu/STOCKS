"""Email delivery of the nightly report.

Two delivery paths:
  1. Brevo HTTPS API (https://api.brevo.com) — used when BREVO_API_KEY is
     set. This is REQUIRED when running in Claude Code cloud containers:
     their egress gateway only relays HTTP(S), so raw SMTP (ports 587/465)
     can never connect there, no matter the credentials.
  2. Plain SMTP with STARTTLS — used otherwise. Works from a normal
     machine/VPS cron where outbound SMTP is allowed.

Every address in EMAIL_TO (comma-separated) receives the report with a
plain-text fallback, the styled HTML body, and the same HTML attached as
a .html file that opens as a full page in a browser.
"""

import base64
import logging
import smtplib
import ssl
from email.message import EmailMessage

import requests

import config

log = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _send_via_brevo(date: str, text_body: str, html_body: str | None) -> bool:
    payload = {
        "sender": {"name": "Nightly Buzz Screener", "email": config.EMAIL_FROM},
        "to": [{"email": addr} for addr in config.EMAIL_TO],
        "subject": f"Nightly Buzz Report — {date}",
        "textContent": text_body,
    }
    if html_body:
        payload["htmlContent"] = html_body
        payload["attachment"] = [
            {
                "name": f"buzz_report_{date}.html",
                "content": base64.b64encode(html_body.encode("utf-8")).decode("ascii"),
            }
        ]

    resp = requests.post(
        BREVO_ENDPOINT,
        json=payload,
        headers={"api-key": config.BREVO_API_KEY, "content-type": "application/json"},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        log.info("Report emailed via Brevo to %d recipient(s): %s",
                 len(config.EMAIL_TO), ", ".join(config.EMAIL_TO))
        return True
    log.error("Brevo API returned %d: %s", resp.status_code, resp.text[:500])
    return False


def _send_via_smtp(date: str, text_body: str, html_body: str | None) -> bool:
    msg = EmailMessage()
    msg["Subject"] = f"Nightly Buzz Report — {date}"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        msg.add_attachment(
            html_body.encode("utf-8"),
            maintype="text",
            subtype="html",
            filename=f"buzz_report_{date}.html",
        )

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
    log.info("Report emailed via SMTP to %d recipient(s): %s",
             len(config.EMAIL_TO), ", ".join(config.EMAIL_TO))
    return True


def send_report(date: str, text_body: str, html_body: str | None = None) -> bool:
    if not config.EMAIL_ENABLED:
        log.info("Email disabled (EMAIL_ENABLED=false), skipping send")
        return False
    if not config.EMAIL_TO:
        log.warning("EMAIL_TO not configured, skipping email")
        return False

    try:
        if config.BREVO_API_KEY:
            return _send_via_brevo(date, text_body, html_body)
        if config.SMTP_HOST:
            return _send_via_smtp(date, text_body, html_body)
        log.warning("Neither BREVO_API_KEY nor SMTP_HOST configured, skipping email")
        return False
    except Exception:
        log.exception("Failed to send report email")
        return False
