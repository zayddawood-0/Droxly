"""api.md §1 request/response shapes (tasks/remediation-plan.md R1)."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_PASSWORD_PATTERN = re.compile(r"(?=.*[A-Za-z])(?=.*\d)")


def _validate_password_strength(value: str) -> str:
    """FR-AUTH-001 — min 8 chars, at least one letter and one number,
    checked at the Pydantic boundary before any hashing or DB write
    (security.md §2.1)."""
    if len(value) < 8 or not _PASSWORD_PATTERN.search(value):
        raise ValueError(
            "Password must be at least 8 characters and include a letter and a number."
        )
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified: bool = False


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    verified: bool = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    plan: str


class PasswordResetRequestRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_label: str | None
    ip_address: str | None
    created_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def _stringify_ip(cls, value: object) -> str | None:
        # asyncpg returns Postgres INET columns as ipaddress.IPv4Address/
        # IPv6Address objects, not str — stringified here so the response
        # schema's declared str type actually matches what it serializes.
        return None if value is None else str(value)
