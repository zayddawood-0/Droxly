"""
tasks/remediation-plan.md R1 §"Key implementation notes" — a minimal
EmailProvider abstraction, mirroring app/ai/llm.py's LLMProvider /
app/ai/embeddings.py's EmbeddingProvider pattern (decisions.md ADR-011/012):
an ABC, a deterministic "fake" default for local dev/tests (zero external
calls, zero cost), and one real implementation behind a settings flag.
Documented as decisions.md ADR-020.
"""

import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings


@dataclass
class SentEmail:
    """
    observability.md §1 — never logged with body content in a real
    provider; FakeEmailProvider records this in-memory shape specifically
    so tests can assert *that* an email was sent and to whom, without ever
    needing the provider to persist or log the body text itself.
    """

    to: str
    subject: str
    body: str


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class FakeEmailProvider(EmailProvider):
    """Deterministic, offline, zero-cost — the active default until SMTP
    settings are configured (mirrors llm_provider/embedding_provider's own
    "fake by default" pattern in core/config.py)."""

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, body=body))


class SMTPEmailProvider(EmailProvider):
    """
    stdlib-only (smtplib/email.message) — no new dependency for a single
    outbound-mail use case, consistent with CLAUDE.md §5's "a new library
    is a deliberate choice, not a convenience reach." Synchronous smtplib
    calls are offloaded to a thread so they don't block the event loop.
    """

    def __init__(
        self, host: str, port: int, username: str | None, password: str | None
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password

    async def send(self, *, to: str, subject: str, body: str) -> None:
        import asyncio

        await asyncio.to_thread(self._send_sync, to, subject, body)

    def _send_sync(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = settings.email_from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


def get_email_provider() -> EmailProvider:
    if settings.email_provider == "smtp" and settings.smtp_host:
        return SMTPEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
        )
    return FakeEmailProvider()
