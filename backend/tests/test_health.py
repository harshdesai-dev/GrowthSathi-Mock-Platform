import pytest
from django.urls import reverse


def test_liveness_does_not_require_database(client):
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_is_available(client):
    response = client.get(reverse("openapi-schema"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi")


@pytest.mark.django_db
def test_readiness_checks_database(client):
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}
