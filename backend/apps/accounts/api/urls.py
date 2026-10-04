from django.urls import path

from .views import (
    CsrfTokenView,
    GoogleAuthView,
    LogoutView,
    MeView,
    OwnerAccessView,
    ProfileView,
    RefreshView,
)

urlpatterns = [
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/google/", GoogleAuthView.as_view(), name="auth-google"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("owner/access/", OwnerAccessView.as_view(), name="owner-access"),
    path("profile/", ProfileView.as_view(), name="student-profile"),
]
