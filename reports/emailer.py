"""SMTP delivery of the nightly report.

Sends a multipart email to every address in EMAIL_TO (comma-separated):
  - plain-text body (fallback for text-only clients)
  - styled HTML body (what most clients render)
  - the same HTML attached as a .html file, so recipients can open the
    full styled page in a browser
"""

import logging
import smtplib
from email.message import EmailMessage

import config

log = logging.getLogger(__name__)


def send_report(date: str, text_body: str, html_body: str | None = None) -> bool:
    if not config.EMAIL_ENABLED:
        log.info("Email disabled (EMAIL_ENABLED=false), skipping send")
        return False
    if not (config.SMTP_HOST and config.EMAIL_TO):
        log.warning("SMTP_HOST or EMAIL_TO not configured, skipping email")
        return False

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

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        log.info("Report emailed to %d recipient(s): %s",
                 len(config.EMAIL_TO), ", ".join(config.EMAIL_TO))
        return True
    except Exception:
        log.exception("Failed to send report email")
        return False
