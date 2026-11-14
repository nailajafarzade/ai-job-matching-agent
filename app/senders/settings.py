"""Read email configuration from environment variables or a local .env file."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from app.config import ENV_FILE


@dataclass(frozen=True)
class EmailSettings:
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    email_from: str | None = None
    dry_run: bool = True

    @classmethod
    def from_env(
        cls,
        env_file: Path = ENV_FILE,
        environ: dict[str, str] | None = None,
    ) -> "EmailSettings":
        values = _read_env_file(env_file)
        values.update(os.environ if environ is None else environ)
        port_text = _clean(values.get("SMTP_PORT"))
        try:
            port = int(port_text) if port_text else None
        except ValueError as error:
            raise ValueError("SMTP_PORT must be an integer") from error

        dry_text = (values.get("EMAIL_DRY_RUN") or "true").strip().casefold()
        if dry_text not in {"true", "false"}:
            raise ValueError("EMAIL_DRY_RUN must be true or false")
        return cls(
            smtp_host=_clean(values.get("SMTP_HOST")),
            smtp_port=port,
            smtp_user=_clean(values.get("SMTP_USER")),
            smtp_password=_clean(values.get("SMTP_PASSWORD")),
            email_from=_clean(values.get("EMAIL_FROM")),
            dry_run=dry_text == "true",
        )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _clean(value: str | None) -> str | None:
    value = value.strip() if value is not None else ""
    return value or None