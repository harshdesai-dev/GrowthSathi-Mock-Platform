"""Read-only plans/index inventory on synthetic Phase 4 load fixtures."""

import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.attempts.models import Attempt  # noqa: E402
from apps.commerce.models import MockAccessGrant  # noqa: E402
from apps.exams.models import MockTest  # noqa: E402


def main():
    if connection.vendor != "postgresql" or not settings.DATABASES["default"]["NAME"].endswith(
        "phase4_load"
    ):
        raise SystemExit("Use a synthetic Phase 4 load database only.")
    student = User.objects.filter(is_staff=False).first()
    mock = MockTest.objects.get()
    queries = {
        "jwt_user": User.objects.filter(pk=student.pk).order_by()[:21],
        "attempt_student_mock": Attempt.objects.filter(student=student, mock_test=mock).order_by(
            "pk"
        )[:1],
        "entitlement": MockAccessGrant.objects.filter(
            student=student,
            mock_test=mock,
            status="ACTIVE",
            source_order_item__order__status="PAID",
        ).values("pk")[:1],
        "mock_scheme": MockTest.objects.select_related("exam_scheme")
        .filter(pk=mock.pk)
        .order_by()[:21],
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename IN ('accounts_user','attempts_attempt',"
            "'commerce_mockaccessgrant','exams_mocktest') ORDER BY tablename,indexname"
        )
        print("INDEXES " + json.dumps(cursor.fetchall()))
        cursor.execute(
            "SELECT name, setting, unit FROM pg_settings WHERE name IN "
            "('max_connections','shared_buffers','work_mem','max_worker_processes','track_io_timing')"
        )
        print("SETTINGS " + json.dumps(cursor.fetchall()))
    for name, query in queries.items():
        print("PLAN " + name + " " + query.explain(analyze=True, buffers=True, format="JSON"))


if __name__ == "__main__":
    main()
