import logging
from typing import Any

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

logger = logging.getLogger(__name__)


def _error_code(data: Any, status_code: int) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if hasattr(detail, "code"):
            return str(detail.code)
    return f"http_{status_code}"


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        if settings.DEBUG:
            return None
        set_rollback()
        logger.error("api_unhandled_exception", exc_info=True)
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong. Please retry."}},
            status=500,
        )

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
