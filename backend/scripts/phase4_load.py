"""Isolated real-HTTP/real-PostgreSQL reliability burst test; never production.

Run after migrate with DATABASE_URL pointing to a NEW database whose name ends
in phase4_load. This script creates synthetic paid fixtures without gateway calls.
No application clock override or synthetic purchase endpoint is shipped in the API.
"""

import argparse
import json
import logging
import os
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import patch

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

import requests  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.wsgi import get_wsgi_application  # noqa: E402
from django.db import connection, connections  # noqa: E402
from rest_framework_simplejwt.tokens import AccessToken  # noqa: E402
from waitress.server import create_server  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.attempts.models import Attempt, StudentResponse  # noqa: E402
from apps.attempts.services import reconcile_expired  # noqa: E402
from tests.attempt_helpers import exam_fixture, paid_student  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--port", type=int, default=8094)
    parser.add_argument("--start-only", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if connection.vendor != "postgresql" or not settings.DATABASES["default"]["NAME"].endswith(
        "phase4_load"
    ):
        raise SystemExit("Refusing: use a dedicated PostgreSQL database ending in phase4_load.")
    if User.objects.exists():
        raise SystemExit("Refusing to mix datasets: use a new, migrated, empty load database.")
    if (
        not 2 <= args.students <= 1000
        or not 1 <= args.concurrency <= 200
        or not 1 <= args.threads <= 64
    ):
        raise SystemExit("Out of bounds load configuration.")
    logging.disable(logging.CRITICAL)
    mock = exam_fixture("MHT_CET_PCM")
    students = []
    for number in range(args.students):
        user = paid_student(mock, number)
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(hours=2))
        students.append({"token": str(token), "attempt": None})
    pc = mock.questions.filter(phase__order=1).first()
    maths = mock.questions.filter(phase__order=2).first()
    pc_option = str(pc.options.first().pk)
    math_option = str(maths.options.first().pk)
    print(
        f"Seeded {args.students} synthetic paid CET students; full 150-question paper.", flush=True
    )
    # Fixture authoring must not pre-warm start-path validation. Each invocation
    # measures a cold process (the first starts also lazily activate SCHEDULED).
    from apps.exams import validation
    from scripts.start_probe import StartProbe

    if hasattr(validation, "_row_field_errors"):
        validation._row_field_errors.cache_clear()

    probe = StartProbe() if args.profile else None
    server = create_server(
        probe.wrap(get_wsgi_application()) if probe else get_wsgi_application(),
        host="127.0.0.1",
        port=args.port,
        threads=args.threads,
        connection_limit=512,
    )
    serving = threading.Thread(target=server.run, daemon=True)
    serving.start()
    report = {
        "students": args.students,
        "client_concurrency": args.concurrency,
        "wsgi_threads": args.threads,
        "database": "PostgreSQL",
        "bursts": [],
    }
    base = f"http://127.0.0.1:{args.port}/api/v1"
    local = threading.local()
    http_outside_app = []

    def request(student, path, method="POST", payload=None, expected=200):
        if not hasattr(local, "session"):
            local.session = requests.Session()
        start = time.perf_counter()
        try:
            response = local.session.request(
                method,
                base + path,
                json=payload,
                headers={"Authorization": f"Bearer {student['token']}"},
                timeout=60,
            )
            elapsed = (time.perf_counter() - start) * 1000
            if "X-Start-Profile-App-Ms" in response.headers:
                http_outside_app.append(elapsed - float(response.headers["X-Start-Profile-App-Ms"]))
            if response.status_code != expected:
                return elapsed, response.status_code, False
            if path.endswith("/start/"):
                student["attempt"] = response.json()["attempt_id"]
            if path.endswith("/paper/"):
                body = response.text
                assert not any(
                    secret in body
                    for secret in ['"is_correct"', '"correct_numeric_answer"', '"explanation_md"']
                )
            return elapsed, response.status_code, True
        except Exception as exc:
            return (time.perf_counter() - start) * 1000, type(exc).__name__, False

    def burst(name, operation, participants=None):
        selected = students if participants is None else participants
        start = time.perf_counter()
        results = list(pool.map(operation, selected))
        duration = time.perf_counter() - start
        durations = sorted(r[0] for r in results)

        def percentile(p):
            return round(durations[min(len(durations) - 1, int((len(durations) - 1) * p))], 2)

        value = {
            "name": name,
            "requests": len(results),
            "seconds": round(duration, 2),
            "requests_per_second": round(len(results) / duration, 2),
            "p50_ms": round(statistics.median(durations), 2),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
            "max_ms": round(max(durations), 2),
            "unexpected_errors": sum(not r[2] for r in results),
            "statuses": dict(Counter(str(r[1]) for r in results)),
        }
        report["bursts"].append(value)
        print(json.dumps(value), flush=True)
        if value["unexpected_errors"]:
            raise AssertionError(f"Unexpected failures in {name}")

    def response(student, question, version, option, expected=200):
        return request(
            student,
            f"/attempts/{student['attempt']}/responses/{question.pk}/",
            "PUT",
            {
                "selected_option": option,
                "numeric_answer": "",
                "marked_for_review": False,
                "mutation_version": version,
            },
            expected,
        )

    try:
        with (
            ThreadPoolExecutor(max_workers=args.concurrency) as pool,
            patch("apps.attempts.services.timezone.now") as clock,
            probe if probe else nullcontext(),
        ):
            phase_time = mock.starts_at + timedelta(minutes=5)
            reference = time.perf_counter()
            clock.side_effect = lambda: (
                phase_time + timedelta(seconds=time.perf_counter() - reference)
            )
            burst(
                "simultaneous_starts", lambda s: request(s, f"/mocks/{mock.pk}/start/", payload={})
            )
            if probe:
                from scripts.start_probe import distribution

                probe.report()
                print("HTTP_OUTSIDE_APP " + json.dumps(distribution(http_outside_app)), flush=True)
            if args.start_only:
                assert Attempt.objects.count() == args.students
                assert Attempt.objects.filter(status="IN_PROGRESS").count() == args.students
                print("START_INTEGRITY PASS: one active attempt per student", flush=True)
                return
            burst("full_pc_paper", lambda s: request(s, f"/attempts/{s['attempt']}/paper/", "GET"))
            burst(
                "synchronized_heartbeat",
                lambda s: request(s, f"/attempts/{s['attempt']}/heartbeat/", payload={}),
            )
            for version in range(1, 4):
                burst(f"autosave_v{version}", lambda s, v=version: response(s, pc, v, pc_option))
            burst("lost_ack_retry", lambda s: response(s, pc, 3, pc_option))
            burst("stale_offline_reconnect", lambda s: response(s, pc, 1, pc_option, 409))
            phase_time = mock.starts_at + timedelta(minutes=90)
            reference = time.perf_counter()
            burst("closed_pc_boundary", lambda s: response(s, pc, 4, pc_option, 409))
            burst(
                "mathematics_phase_fetch",
                lambda s: request(s, f"/attempts/{s['attempt']}/paper/", "GET"),
            )
            burst("mathematics_save", lambda s: response(s, maths, 1, math_option))
            manual = students[: args.students // 2]
            automatic = students[args.students // 2 :]
            burst(
                "manual_submit",
                lambda s: request(s, f"/attempts/{s['attempt']}/submit/", payload={}),
                manual,
            )
            burst(
                "duplicate_submit",
                lambda s: request(s, f"/attempts/{s['attempt']}/submit/", payload={}),
                manual,
            )
            phase_time = mock.ends_at
            reference = time.perf_counter()
            burst(
                "deadline_late_save", lambda s: response(s, maths, 2, math_option, 409), automatic
            )
            burst(
                "deadline_recovery",
                lambda s: request(s, f"/attempts/{s['attempt']}/heartbeat/", payload={}),
                automatic,
            )
            assert reconcile_expired() == 0
        assert Attempt.objects.count() == args.students
        assert Attempt.objects.filter(status="SUBMITTED").count() == len(manual)
        assert Attempt.objects.filter(status="AUTO_SUBMITTED").count() == len(automatic)
        assert StudentResponse.objects.count() == args.students * 2
        assert (
            StudentResponse.objects.filter(question=pc, mutation_version=3).count() == args.students
        )
        assert (
            StudentResponse.objects.filter(question=maths, mutation_version=1).count()
            == args.students
        )
        report["integrity"] = (
            "PASS: unique attempts, exact terminal counts, exact response counts and versions; "
            "no late or stale overwrites"
        )
        report["total_requests"] = sum(b["requests"] for b in report["bursts"])
        print("FINAL " + json.dumps(report), flush=True)
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        connections.close_all()


if __name__ == "__main__":
    main()
