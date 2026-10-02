from django.db import connections
from django.db.utils import OperationalError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class LivenessView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(responses={200: dict})
    def get(self, request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(responses={200: dict, 503: dict})
    def get(self, request) -> Response:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            return Response(
                {"status": "unavailable", "checks": {"database": "unavailable"}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"status": "ok", "checks": {"database": "ok"}})
