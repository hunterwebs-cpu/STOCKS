"""SMTP delivery of the nightly report."""

import logging
import smtplib
from email.mime.text import MIMEText

import config

log = logging.getLogger(__name__)


def send_report(date: str, body: str) -> bool:
    if not config.EMAIL_ENABLED:
        log.info("Email disabled (EMAIL_ENABLED=false), skipping send")
        return False
    if not (config.SMTP_HOST and config.EMAIL_TO):
        log.warning("SMTP_HOST or EMAIL_TO not configured, skipping email")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Nightly Buzz Report — {date}"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        log.info("Report emailed to %s", ", ".join(config.EMAIL_TO))
        return True
    except Exception:
        log.exception("Failed to send report email")
        return False
