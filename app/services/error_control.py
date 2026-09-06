"""Shared fail-closed error handling for Centinela integration boundaries.

The goal is not to catch every exception. Internal programming errors should remain
visible in tests and logs. This module standardizes only boundary failures where a
user-facing operation needs a safe, actionable result without leaking credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class ErrorCategory(StrEnum):
    CONFIG = "config"
    AUTH = "auth"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    FILESYSTEM = "filesystem"
    SUBPROCESS = "subprocess"
    MEDIA = "media"
    DEPENDENCY = "dependency"
    VALIDATION = "validation"
    UPSTREAM = "upstream"
    UNKNOWN = "unknown"


_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|apikey)\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret)"
        r"\s*[:=]\s*)[^\s,;]+"
    ),
)


def redact_secrets(value: object) -> str:
    """Return log-safe text with common credential forms replaced."""
    text = str(value)
    for pattern in _REDACTION_PATTERNS:
        text = pattern.sub(r"\1***REDACTED***", text)
    return text


@dataclass(slots=True)
class ErrorContext:
    operation: str
    component: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def safe_details(self) -> dict[str, str]:
        return {str(key): redact_secrets(value) for key, value in self.details.items()}


class CentinelaError(RuntimeError):
    """Typed boundary error with a safe public message and machine-readable code."""

    def __init__(
        self,
        *,
        code: str,
        category: ErrorCategory,
        message: str,
        context: ErrorContext,
        retryable: bool = False,
        cause: BaseException | None = None,
    ) -> None:
        self.code = code
        self.category = category
        self.safe_message = redact_secrets(message)
        self.context = context
        self.retryable = bool(retryable)
        self.cause = cause
        super().__init__(self.safe_message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "message": self.safe_message,
            "retryable": self.retryable,
            "operation": self.context.operation,
            "component": self.context.component,
            "details": self.context.safe_details(),
        }


def boundary_error(
    *,
    code: str,
    category: ErrorCategory,
    message: str,
    operation: str,
    component: str = "",
    retryable: bool = False,
    details: Mapping[str, Any] | None = None,
    cause: BaseException | None = None,
) -> CentinelaError:
    return CentinelaError(
        code=code,
        category=category,
        message=message,
        context=ErrorContext(
            operation=operation,
            component=component,
            details=dict(details or {}),
        ),
        retryable=retryable,
        cause=cause,
    )


def validate_local_media_file(
    path: str | Path,
    *,
    operation: str,
    allowed_extensions: set[str] | frozenset[str] | None = None,
    max_size_bytes: int | None = None,
) -> Path:
    """Validate a local upload candidate before opening or sending it anywhere."""
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise boundary_error(
            code="media_not_found",
            category=ErrorCategory.FILESYSTEM,
            message=f"No se puede acceder al archivo de vídeo: {candidate}",
            operation=operation,
            component="local_media",
            cause=exc,
        ) from exc

    if not resolved.is_file():
        raise boundary_error(
            code="media_not_file",
            category=ErrorCategory.VALIDATION,
            message="La ruta seleccionada no es un archivo regular.",
            operation=operation,
            component="local_media",
            details={"path": resolved},
        )

    if allowed_extensions:
        normalized = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in allowed_extensions}
        if resolved.suffix.lower() not in normalized:
            raise boundary_error(
                code="media_extension_not_allowed",
                category=ErrorCategory.MEDIA,
                message=f"Formato de vídeo no admitido: {resolved.suffix or '(sin extensión)'}",
                operation=operation,
                component="local_media",
                details={"path": resolved},
            )

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise boundary_error(
            code="media_stat_failed",
            category=ErrorCategory.FILESYSTEM,
            message="No se pudo leer el tamaño del archivo de vídeo.",
            operation=operation,
            component="local_media",
            cause=exc,
        ) from exc

    if size <= 0:
        raise boundary_error(
            code="media_empty",
            category=ErrorCategory.MEDIA,
            message="El archivo de vídeo está vacío.",
            operation=operation,
            component="local_media",
        )
    if max_size_bytes is not None and size > max_size_bytes:
        raise boundary_error(
            code="media_too_large",
            category=ErrorCategory.MEDIA,
            message="El archivo supera el límite permitido por este adaptador.",
            operation=operation,
            component="local_media",
            details={"size_bytes": size, "max_size_bytes": max_size_bytes},
        )
    return resolved


def is_retryable_http_status(status_code: int) -> bool:
    """Retry only throttling and transient server failures; never permanent 4xx."""
    return status_code == 429 or 500 <= status_code <= 599
