"""Build a local application package for a human to submit."""
import re
import shutil
from pathlib import Path

from app.config import OUTBOX_DIR
from app.senders.base import SendResult, SenderError


class ManualPackageSender:
    def __init__(self, outbox_dir: Path = OUTBOX_DIR, match_explanation: str = ""):
        self.outbox_dir = outbox_dir
        self.match_explanation = match_explanation

    def send(self, application, job, cv_path: Path | None) -> SendResult:
        if application.status != "approved":
            raise SenderError("Only approved applications can be packaged")
        if not application.letter_text or not application.letter_text.strip():
            raise SenderError("The application has no cover letter")

        package_dir = self.outbox_dir / f"{job.id}_{_company_slug(job.company)}"
        package_dir.mkdir(parents=True, exist_ok=True)
        copied_cv = None
        if cv_path is not None and cv_path.is_file():
            copied_cv = package_dir / cv_path.name
            shutil.copy2(cv_path, copied_cv)

        (package_dir / "letter.txt").write_text(application.letter_text, encoding="utf-8")
        (package_dir / "job.txt").write_text(
            "\n".join(
                [
                    f"Title: {job.title}",
                    f"Company: {job.company}",
                    f"Link: {job.url or 'Not provided'}",
                    f"Source: {job.source}",
                    "",
                    "Match explanation:",
                    self.match_explanation or "No match explanation is available.",
                ]
            ),
            encoding="utf-8",
        )
        readme = [f"Apply here: {job.url or 'No application link is available.'}"]
        if copied_cv is None:
            readme.append("Selected CV PDF is missing. Add the owner's CV before applying.")
        else:
            readme.append(f"CV included: {copied_cv.name}")
        (package_dir / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
        message = "Manual application package is ready."
        if copied_cv is None:
            message += " The selected CV PDF was missing and was not copied."
        return SendResult("manual_package", "package_ready", package_dir, message)


def _company_slug(company: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", company).strip(".-_")
    return (slug or "company")[:80]