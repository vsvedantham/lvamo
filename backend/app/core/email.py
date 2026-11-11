"""Outgoing email for every vertical, behind one small interface so the
provider can change without touching callers (core principle 7).

Two senders:
- `smtp`: any SMTP server. Production uses Zoho Mail (help@lvamo.com).
- `console`: writes the message to the log instead of sending it. The default,
  so local dev and tests never send real mail.

Picked by EMAIL_BACKEND. smtplib is blocking, so the SMTP send runs in a
worker thread.
"""
import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from app.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSendError(Exception):
    """The provider refused or couldn't be reached. Message is safe to log,
    never shown to users."""


class EmailSender(Protocol):
    async def send(self, message: OutgoingEmail) -> None: ...


def _build(message: OutgoingEmail) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((settings.email_from_name, settings.email_from_address))
    msg["To"] = message.to
    msg["Subject"] = message.subject
    if settings.email_reply_to:
        msg["Reply-To"] = settings.email_reply_to
    msg["Message-ID"] = make_msgid(domain=settings.email_from_address.split("@")[-1])
    msg.set_content(message.text)
    if message.html:
        msg.add_alternative(message.html, subtype="html")
    return msg


class SmtpEmailSender:
    def __init__(self, host: str, port: int, username: str, password: str, security: str):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.security = security  # "ssl" (port 465) or "starttls" (port 587)

    def _send_blocking(self, msg: EmailMessage) -> None:
        context = ssl.create_default_context()
        timeout = 20
        if self.security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=timeout)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=timeout)
        with server:
            if self.security == "starttls":
                server.starttls(context=context)
            server.login(self.username, self.password)
            server.send_message(msg)

    async def send(self, message: OutgoingEmail) -> None:
        try:
            await asyncio.to_thread(self._send_blocking, _build(message))
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP send to {self.host}:{self.port} failed: {exc!r}") from exc


class ConsoleEmailSender:
    """Logs instead of sending. Keeps the last messages for tests."""

    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []

    async def send(self, message: OutgoingEmail) -> None:
        self.outbox.append(message)
        del self.outbox[:-50]
        log.warning("EMAIL (console, not sent) to=%s subject=%r\n%s", message.to, message.subject, message.text)


_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is None:
        if settings.email_backend == "smtp":
            _sender = SmtpEmailSender(
                settings.smtp_host, settings.smtp_port,
                settings.smtp_username, settings.smtp_password, settings.smtp_security,
            )
        else:
            _sender = ConsoleEmailSender()
    return _sender


def set_email_sender(sender: EmailSender | None) -> None:
    """For tests: swap in a fake (None goes back to the configured one)."""
    global _sender
    _sender = sender
