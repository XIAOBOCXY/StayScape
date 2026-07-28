from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        field: str | None = None,
        retryable: bool = False,
        suggestion: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.retryable = retryable
        self.suggestion = suggestion
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        error = {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "retryable": self.retryable,
            "suggestion": self.suggestion,
        }
        if self.details is not None:
            error["details"] = self.details
        return {"success": False, "error": error}

