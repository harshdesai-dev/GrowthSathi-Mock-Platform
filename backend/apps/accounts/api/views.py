from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import (
    GoogleTokenVerificationError,
    IdentityConflictError,
    InactiveUserError,
    resolve_google_identity,
    verify_google_id_token,
)
from apps.accounts.sessions import revoke_session, rotate_session
from apps.common.throttles import LoginThrottle, ReadThrottle, SessionThrottle

from .serializers import (
    CsrfTokenSerializer,
    GoogleAuthSerializer,
    MeSerializer,
    RefreshSessionSerializer,
    SessionSerializer,
    StudentProfileSerializer,
)


class PublicAuthenticationError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "authentication_failed"


class IdentityConflictApiError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "identity_conflict"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _session_response(user, *, status_code: int = status.HTTP_200_OK) -> Response:
    refresh = RefreshToken.for_user(user)
    response = Response(
        {
            "access_token": str(refresh.access_token),
            "token_type": "Bearer",
            "expires_in": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            "user": MeSerializer(user).data,
        },
        status=status_code,
    )
    _set_refresh_cookie(response, str(refresh))
    return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: CsrfTokenSerializer})
    def get(self, request) -> Response:
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class GoogleAuthView(APIView):
    throttle_classes = [LoginThrottle]
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={200: SessionSerializer, 201: SessionSerializer},
    )
    def post(self, request) -> Response:
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            identity = verify_google_id_token(serializer.validated_data["credential"])
            user, created = resolve_google_identity(identity)
        except GoogleTokenVerificationError as exc:
            raise PublicAuthenticationError(str(exc), code="invalid_google_token") from exc
        except IdentityConflictError as exc:
            raise IdentityConflictApiError(
                "This Google identity conflicts with an existing account.",
                code="identity_conflict",
            ) from exc
        except InactiveUserError as exc:
            raise PublicAuthenticationError(
                "This account is disabled.", code="account_disabled"
            ) from exc
        except ImproperlyConfigured as exc:
            raise PublicAuthenticationError(
                "Google authentication is not configured.", code="auth_not_configured"
            ) from exc

        get_token(request)
        return _session_response(
            user,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class RefreshView(APIView):
    throttle_classes = [SessionThrottle]
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: RefreshSessionSerializer})
    def post(self, request) -> Response:
        token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not token:
            raise PublicAuthenticationError(
                "A refresh session is required.", code="no_refresh_token"
            )
        try:
            data = rotate_session(token)
        except TokenError as exc:
            raise PublicAuthenticationError(
                "The refresh session is invalid.", code="invalid_refresh"
            ) from exc
        except InactiveUserError as exc:
            raise PublicAuthenticationError(
                "This account is disabled.", code="account_disabled"
            ) from exc

        response = Response(
            {
                "access_token": data["access"],
                "token_type": "Bearer",
                "expires_in": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            }
        )
        _set_refresh_cookie(response, data["refresh"])
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request) -> Response:
        token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if token:
            try:
                revoke_session(token)
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _delete_refresh_cookie(response)
        return response


class MeView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MeSerializer})
    def get(self, request) -> Response:
        return Response(MeSerializer(request.user).data)


class ProfileView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: StudentProfileSerializer})
    def get(self, request) -> Response:
        return Response(StudentProfileSerializer(request.user.profile).data)

    @extend_schema(request=StudentProfileSerializer, responses={200: StudentProfileSerializer})
    def patch(self, request) -> Response:
        serializer = StudentProfileSerializer(
            request.user.profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
