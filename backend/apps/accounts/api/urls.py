from django.urls import path

from .owner_questions import (
    OwnerMockQuestionDetailView,
    OwnerMockQuestionImportCommitView,
    OwnerMockQuestionImportPreviewView,
    OwnerMockQuestionsView,
    OwnerQuestionTemplateView,
)
from .views import (
    CsrfTokenView,
    GoogleAuthView,
    LogoutView,
    MeView,
    OwnerAccessView,
    OwnerMockDetailView,
    OwnerMockOptionsView,
    OwnerMocksView,
    OwnerOverviewView,
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
    path("owner/overview/", OwnerOverviewView.as_view(), name="owner-overview"),
    path("owner/mocks/", OwnerMocksView.as_view(), name="owner-mocks"),
    path("owner/mock-options/", OwnerMockOptionsView.as_view(), name="owner-mock-options"),
    path("owner/mocks/<uuid:mock_id>/", OwnerMockDetailView.as_view(), name="owner-mock-detail"),
    path(
        "owner/mocks/<uuid:mock_id>/questions/",
        OwnerMockQuestionsView.as_view(),
        name="owner-mock-questions",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/questions/<uuid:question_id>/",
        OwnerMockQuestionDetailView.as_view(),
        name="owner-mock-question-detail",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/questions/import/preview/",
        OwnerMockQuestionImportPreviewView.as_view(),
        name="owner-question-import-preview",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/questions/import/commit/",
        OwnerMockQuestionImportCommitView.as_view(),
        name="owner-question-import-commit",
    ),
    path(
        "owner/question-import/template/<str:file_format>/",
        OwnerQuestionTemplateView.as_view(),
        name="owner-question-import-template",
    ),
    path("profile/", ProfileView.as_view(), name="student-profile"),
]
