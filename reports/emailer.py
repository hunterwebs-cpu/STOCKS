import smtplib
from email.mime.text import MIMEText

import config


def send_report(subject: str, body: str) -> None:
    """Send the report via SMTP. Skips if EMAIL_DRY_RUN is true."""
    if config.EMAIL_DRY_RUN:
        print("[emailer] DRY RUN — email not sent.")
        return

    if not config.SMTP_USER or not config.EMAIL_TO:
        print("[emailer] SMTP credentials or recipient not configured; skipping email.")
        return

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM or config.SMTP_USER
    msg["To"] = config.EMAIL_TO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(
                msg["From"],
                [config.EMAIL_TO],
                msg.as_string(),
            )
        print(f"[emailer] Report sent to {config.EMAIL_TO}")
    except Exception as e:
        print(f"[emailer] Failed to send email: {e}")
        raise
