from django.http import JsonResponse


def csrf_failure(request, reason="") -> JsonResponse:
    return JsonResponse(
        {
            "error": {
                "code": "csrf_failed",
                "message": "CSRF validation failed.",
                "details": None,
            }
        },
        status=403,
    )
