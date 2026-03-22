from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class RequestContractError(AppError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details or {},
        )


class StateContractError(AppError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int = 500,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details or {},
        )


class DependencyError(AppError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int = 502,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details or {},
        )
