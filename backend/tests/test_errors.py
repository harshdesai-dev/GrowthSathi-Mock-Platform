from django.urls import path
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.common.api.exceptions import api_exception_handler


class InvalidView(APIView):
    def get(self, request):
        raise ValidationError({"field": ["This field is required."]})


urlpatterns = [path("invalid/", InvalidView.as_view())]


def test_exception_handler_uses_shared_envelope(settings):
    settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] = (
        "apps.common.api.exceptions.api_exception_handler"
    )
    request = APIRequestFactory().get("/invalid/")

    response = InvalidView.as_view()(request)
    response.render()

    assert response.status_code == 400
    assert response.data["error"]["code"] == "http_400"
    assert response.data["error"]["message"] == "The request could not be completed."
    assert response.data["error"]["details"] == {"field": ["This field is required."]}


def test_exception_handler_returns_none_for_unknown_exception_in_debug(settings):
    settings.DEBUG = True
    assert api_exception_handler(RuntimeError("boom"), {}) is None
