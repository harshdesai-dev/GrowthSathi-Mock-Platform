from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler


def _error_code(data: Any, status_code: int) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if hasattr(detail, "code"):
            return str(detail.code)
    return f"http_{status_code}"


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None

    original_data = response.data
    if isinstance(original_data, dict) and "detail" in original_data:
        message = str(original_data["detail"])
    else:
        message = "The request could not be completed."

    response.data = {
        "error": {
            "code": _error_code(original_data, response.status_code),
            "message": message,
            "details": original_data,
        }
    }
    return response
