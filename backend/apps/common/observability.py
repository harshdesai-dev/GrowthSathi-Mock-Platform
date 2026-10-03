"""Small, payload-free operational logs. Never serialize requests or exception values."""

import json
import logging
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

request_id = ContextVar("request_id", default="")
logger = logging.getLogger(__name__)


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id.get(),
        }
        # Only our reviewed application logs have allowlisted messages. Framework/provider
        # messages can embed URLs, credentials or database values, even without exc_info.
        data["event"] = record.getMessage() if record.name.startswith("apps.") else record.name
        if record.exc_info and record.exc_info[0]:
            data["exception_type"] = record.exc_info[0].__name__
            data["frames"] = [
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(data)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation = uuid.uuid4().hex
        token = request_id.set(correlation)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = correlation
            if request.path.startswith(("/api/", "/admin/")):
                response["Cache-Control"] = "private, no-store"
            if response.status_code >= 400:
                match = getattr(request, "resolver_match", None)
                logger.warning(
                    "request_rejected route=%s status=%s duration_ms=%s",
                    match.route if match else "unresolved",
                    response.status_code,
                    round((time.monotonic() - started) * 1000),
                )
            return response
        finally:
            request_id.reset(token)
