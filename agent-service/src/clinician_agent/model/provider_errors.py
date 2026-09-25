"""Normalize OpenAI-compatible provider failures to domain errors."""

from __future__ import annotations

import json
import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from pydantic import ValidationError

from clinician_agent.errors import AppError

logger = logging.getLogger(__name__)


def raise_model_provider_error(exc: BaseException) -> None:
    """Map a provider exception to ``AppError`` and raise it."""
    raise normalize_model_provider_error(exc) from exc


def normalize_model_provider_error(exc: BaseException) -> AppError:
    """Map a provider exception to a stable ``AppError``."""
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, ValidationError):
        logger.warning("Model output failed schema validation")
        return AppError("model_output_invalid", "Model output failed validation", 502)
    if isinstance(exc, json.JSONDecodeError):
        logger.warning("Model output was not valid JSON")
        return AppError("model_output_invalid", "Model output was not valid JSON", 502)
    if isinstance(exc, APITimeoutError):
        logger.warning("Model provider request timed out")
        return AppError("model_timeout", "Model provider timed out", 503)
    if isinstance(exc, AuthenticationError):
        logger.warning("Model provider authentication failed")
        return AppError("model_auth_failed", "Model provider authentication failed", 503)
    if isinstance(exc, RateLimitError):
        logger.warning("Model provider rate limited")
        return AppError("model_rate_limited", "Model provider rate limited", 503)
    if isinstance(exc, APIConnectionError):
        logger.warning("Model provider connection failed")
        return AppError("model_provider_unavailable", "Model provider unavailable", 503)
    if isinstance(exc, BadRequestError):
        logger.warning("Model provider rejected request: %s", _safe_status(exc))
        return AppError("model_request_rejected", "Model provider rejected the request", 502)
    if isinstance(exc, APIStatusError):
        status_code = exc.status_code
        if status_code == 429:
            return AppError("model_rate_limited", "Model provider rate limited", 503)
        if 400 <= status_code < 500:
            logger.warning("Model provider client error status=%s", status_code)
            return AppError("model_request_rejected", "Model provider rejected the request", 502)
        logger.warning("Model provider server error status=%s", status_code)
        return AppError("model_provider_unavailable", "Model provider unavailable", 503)
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if status_code == 429:
            return AppError("model_rate_limited", "Model provider rate limited", 503)
        if 400 <= status_code < 500:
            logger.warning("Model provider client error status=%s", status_code)
            return AppError("model_request_rejected", "Model provider rejected the request", 502)
        logger.warning("Model provider server error status=%s", status_code)
        return AppError("model_provider_unavailable", "Model provider unavailable", 503)
    logger.warning("Unexpected model provider failure: %s", type(exc).__name__)
    return AppError("model_provider_unavailable", "Model provider unavailable", 503)


def _safe_status(exc: BaseException) -> str:
    """Return a non-sensitive status hint for logs."""
    response = getattr(exc, "response", None)
    if response is None:
        return "unknown"
    status = getattr(response, "status_code", None)
    return str(status) if status is not None else "unknown"
