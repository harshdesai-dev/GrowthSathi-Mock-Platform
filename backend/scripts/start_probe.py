"""Opt-in, test-process-only start profiling. Never installed in application settings.

Spans are inclusive and overlap: do not add their percentiles. SQL execute time is
client-observed wall time, including driver/GIL scheduling, not PostgreSQL CPU time.
No JWTs, response values or SQL parameter values are emitted.
"""

import json
import re
import threading
from collections import Counter, defaultdict
from contextlib import ExitStack
from contextvars import ContextVar
from functools import wraps
from time import perf_counter, thread_time
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.query import QuerySet
from rest_framework.renderers import JSONRenderer
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.attempts import services

active = ContextVar("start_profile", default=None)


def distribution(values):
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "total": round(sum(ordered), 3),
        **{
            name: round(ordered[int((len(ordered) - 1) * fraction)], 3) if ordered else 0
            for name, fraction in [("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1)]
        },
    }


class StartProbe:
    def __init__(self):
        self.rows = []
        self.waits = Counter()
        self.max_connections = 0
        self.max_blocked = 0
        self.stop = threading.Event()
        self.stack = ExitStack()
        self.sampler = None

    @staticmethod
    def timed(name, operation):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            row = active.get()
            if row is None:
                return operation(*args, **kwargs)
            started, cpu = perf_counter(), thread_time()
            try:
                return operation(*args, **kwargs)
            finally:
                row["wall"][name] += (perf_counter() - started) * 1000
                row["cpu"][name] += (thread_time() - cpu) * 1000
                row["calls"][name] += 1

        return wrapped

    def __enter__(self):
        for target, name, label in [
            (services, "start_attempt", "start_service"),
            (services, "validate_paper", "paper_validation"),
            (services, "has_access", "entitlement"),
            (services, "state_data", "state_serialization"),
            (JWTAuthentication, "authenticate", "jwt_authenticate"),
            (JSONRenderer, "render", "json_render"),
            (BaseDatabaseWrapper, "connect", "connection_open"),
            (BaseDatabaseWrapper, "_commit", "transaction_commit"),
            (transaction.Atomic, "__enter__", "atomic_enter"),
        ]:
            self.stack.enter_context(
                patch.object(target, name, self.timed(label, getattr(target, name)))
            )
        original = QuerySet._fetch_all

        def fetched(query):
            if query._result_cache is not None:
                return original(query)
            name = f"orm_{query.model._meta.model_name}"
            if query.query.select_for_update:
                name += "_lock"
            return self.timed(name, original)(query)

        self.stack.enter_context(patch.object(QuerySet, "_fetch_all", fetched))
        self.sampler = threading.Thread(target=self.sample, daemon=True)
        self.sampler.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.sampler.join(timeout=5)
        self.stack.close()

    def sample(self):
        try:
            while not self.stop.wait(0.05):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT state, wait_event_type, wait_event, "
                        "cardinality(pg_blocking_pids(pid)) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid()"
                    )
                    rows = cursor.fetchall()
                self.max_connections = max(self.max_connections, len(rows))
                self.max_blocked = max(self.max_blocked, sum(bool(row[3]) for row in rows))
                self.waits.update(f"{row[0]}/{row[1]}/{row[2]}" for row in rows)
        finally:
            connections.close_all()

    def sql(self, execute, sql, params, many, context):
        row = active.get()
        if row is None:
            return execute(sql, params, many, context)
        table = re.search(r'(?:FROM|INTO|UPDATE) "([a-z_]+)"', sql)
        kind = sql.split()[0] + ":" + (table[1] if table else "other")
        if "FOR UPDATE" in sql:
            kind += ":lock"
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            row["sql_ms"][kind] += (perf_counter() - started) * 1000
            row["sql_count"][kind] += 1

    def wrap(self, application):
        def wsgi(environ, start_response):
            if not environ.get("PATH_INFO", "").endswith("/start/"):
                return application(environ, start_response)
            row = {
                name: defaultdict(float) for name in ["wall", "cpu", "calls", "sql_ms", "sql_count"]
            }
            token = active.set(row)
            started, cpu = perf_counter(), thread_time()

            def responding(status, headers, exc_info=None):
                headers.append(("X-Start-Profile-App-Ms", str((perf_counter() - started) * 1000)))
                return start_response(status, headers, exc_info)

            try:
                with connection.execute_wrapper(self.sql):
                    result = application(environ, responding)
                    try:
                        return list(result)
                    finally:
                        if hasattr(result, "close"):
                            result.close()
            finally:
                row["wall"]["wsgi_application"] = (perf_counter() - started) * 1000
                row["cpu"]["wsgi_application"] = (thread_time() - cpu) * 1000
                self.rows.append(row)
                active.reset(token)

        return wsgi

    def report(self):
        report = {}
        for section in ["wall", "cpu", "calls", "sql_ms", "sql_count"]:
            names = sorted({name for row in self.rows for name in row[section]})
            report[section] = {
                name: distribution([row[section].get(name, 0) for row in self.rows])
                for name in names
            }
        report["pg_wait_samples"] = dict(self.waits)
        report["max_pg_connections"] = self.max_connections
        report["max_pg_blocked"] = self.max_blocked
        print("PROFILE " + json.dumps(report), flush=True)
