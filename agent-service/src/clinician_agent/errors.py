"""HTTP and domain error helpers."""

from fastapi import HTTPException, status

from clinician_agent.schemas import ErrorBody, Identifier


class AppError(Exception):
    """Domain error mapped to HTTP responses."""

    def __init__(self, code: Identifier, message: str, status_code: int) -> None:
        """Store stable error metadata."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_body(code: Identifier, message: str) -> dict[str, object]:
    """Serialize a contracted error payload."""
    return ErrorBody(code=code, message=message).model_dump()


def conflict(code: Identifier, message: str) -> HTTPException:
    """Return a 409 conflict."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=error_body(code, message),
    )


def forbidden(code: Identifier = "forbidden", message: str = "Forbidden") -> HTTPException:
    """Return a 403 response."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_body(code, message),
    )


def not_found(code: Identifier = "not_found", message: str = "Not found") -> HTTPException:
    """Return a 404 response."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_body(code, message),
    )


def unprocessable(code: Identifier, message: str) -> HTTPException:
    """Return a 422 validation failure."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=error_body(code, message),
    )


def service_unavailable(code: Identifier, message: str) -> HTTPException:
    """Return a 503 dependency failure."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=error_body(code, message),
    )


def bad_gateway(code: Identifier, message: str) -> HTTPException:
    """Return a 502 invalid dependency output."""
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=error_body(code, message),
    )
