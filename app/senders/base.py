"""Shared application sender types."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    mode: str
    status: str
    path: Path | None
    message: str


class SenderError(RuntimeError):
    """A sender could not safely complete its requested action."""


class ApplicationSender(Protocol):
    def send(self, application, job, cv_path: Path | None) -> SendResult:
        """Prepare a package or send an approved application."""