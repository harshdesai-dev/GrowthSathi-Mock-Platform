"""Initial sizing for staging measurement, not a 500-student capacity guarantee."""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "3"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 90
graceful_timeout = 90
keepalive = 5
max_requests = 0  # Avoid periodic worker recycling during an exam burst.
accesslog = "-"
# Excludes query strings, IP, cookies, referer, authorization and user agent.
access_log_format = "%(s)s %(M)sms %(m)s request_id=%({x-request-id}o)s"
errorlog = "-"
capture_output = True
