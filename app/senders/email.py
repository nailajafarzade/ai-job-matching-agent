"""Create a dry-run email or send an approved application through SMTP."""
from email.message import EmailMessage
from pathlib import Path
import re
import smtplib

from app.config import OUTBOX_DIR
from app.senders.base import SendResult, SenderError
from app.senders.settings import EmailSettings


class EmailSender:
    def __init__(self, settings: EmailSettings, outbox_dir: Path = OUTBOX_DIR):
        self.settings = settings
        self.outbox_dir = outbox_dir

    def send(self, application, job, cv_path: Path | None) -> SendResult:
        if application.status != "approved":
            raise SenderError("Only approved applications can be emailed")
        if not job.apply_email:
            raise SenderError("The job has no application email address")
        if not application.letter_text or not application.letter_text.strip():
            raise SenderError("The application has no cover letter")
        if cv_path is None or not cv_path.is_file():
            raise SenderError("The selected CV PDF is missing; add it before sending email")
        if not self.settings.email_from:
            raise SenderError("EMAIL_FROM is required for email delivery")

        message = _build_message(application, job, cv_path, self.settings.email_from)
        if self.settings.dry_run:
            path = self.outbox_dir / f"{application.id}_{job.id}_{_company_slug(job.company)}.eml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(message.as_bytes())
            return SendResult(
                "dry_run",
                "package_ready",
                path,
                "Dry-run email saved locally; no SMTP connection was made.",
            )

        self._send_real(message)
        return SendResult("real_email", "sent", None, "Email sent successfully.")

    def _send_real(self, message: EmailMessage) -> None:
        settings = self.settings
        if not all((settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password)):
            raise SenderError("SMTP_HOST, SMTP_PORT, SMTP_USER, and SMTP_PASSWORD are required for real email")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
        except Exception:
            raise SenderError("Email delivery failed; check the SMTP settings") from None


def _build_message(application, job, cv_path: Path, email_from: str) -> EmailMessage:
    message = EmailMessage()
    message["To"] = job.apply_email
    message["From"] = email_from
    title = re.sub(r"[\r\n]+", " ", job.title).strip()
    message["Subject"] = f"Application: {title}"
    message.set_content(application.letter_text)
    message.add_attachment(
        cv_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=cv_path.name,
    )
    return message


def _company_slug(company: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", company).strip(".-_")
    return (slug or "company")[:80]