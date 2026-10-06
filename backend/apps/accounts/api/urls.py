from django.urls import path

from .owner_dashboard import (
    OwnerAnswerCorrectionView,
    OwnerMockResultsView,
    OwnerMockTransitionView,
    OwnerPaymentDetailView,
    OwnerPaymentReconcileView,
    OwnerPaymentsView,
    OwnerResultCalculateView,
    OwnerResultPublishView,
    OwnerResultReconcileView,
    OwnerResultsView,
    OwnerResultVerifyView,
    OwnerStudentDetailView,
    OwnerStudentsView,
)
from .owner_offers import OwnerOfferActivationView, OwnerOfferDetailView, OwnerOffersView
from .owner_operations import OwnerMockPaperValidationView, OwnerMockRulesVerificationView
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
    path("owner/offers/", OwnerOffersView.as_view(), name="owner-offers"),
    path(
        "owner/offers/<uuid:offer_id>/",
        OwnerOfferDetailView.as_view(),
        name="owner-offer-detail",
    ),
    path(
        "owner/offers/<uuid:offer_id>/activation/",
        OwnerOfferActivationView.as_view(),
        name="owner-offer-activation",
    ),
    path("owner/mock-options/", OwnerMockOptionsView.as_view(), name="owner-mock-options"),
    path("owner/mocks/<uuid:mock_id>/", OwnerMockDetailView.as_view(), name="owner-mock-detail"),
    path(
        "owner/mocks/<uuid:mock_id>/transition/",
        OwnerMockTransitionView.as_view(),
        name="owner-mock-transition",
    ),
    path("owner/results/", OwnerResultsView.as_view(), name="owner-results"),
    path(
        "owner/mocks/<uuid:mock_id>/results/",
        OwnerMockResultsView.as_view(),
        name="owner-mock-results",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/results/reconcile/",
        OwnerResultReconcileView.as_view(),
        name="owner-result-reconcile",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/results/verify/",
        OwnerResultVerifyView.as_view(),
        name="owner-result-verify",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/results/<uuid:run_id>/calculate/",
        OwnerResultCalculateView.as_view(),
        name="owner-result-calculate",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/results/<uuid:run_id>/publish/",
        OwnerResultPublishView.as_view(),
        name="owner-result-publish",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/results/correct-answer/",
        OwnerAnswerCorrectionView.as_view(),
        name="owner-answer-correction",
    ),
    path("owner/students/", OwnerStudentsView.as_view(), name="owner-students"),
    path(
        "owner/students/<uuid:student_id>/",
        OwnerStudentDetailView.as_view(),
        name="owner-student-detail",
    ),
    path("owner/payments/", OwnerPaymentsView.as_view(), name="owner-payments"),
    path(
        "owner/payments/<uuid:order_id>/",
        OwnerPaymentDetailView.as_view(),
        name="owner-payment-detail",
    ),
    path(
        "owner/payments/<uuid:order_id>/reconcile/",
        OwnerPaymentReconcileView.as_view(),
        name="owner-payment-reconcile",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/questions/",
        OwnerMockQuestionsView.as_view(),
        name="owner-mock-questions",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/validate/",
        OwnerMockPaperValidationView.as_view(),
        name="owner-mock-validate",
    ),
    path(
        "owner/mocks/<uuid:mock_id>/verify-rules/",
        OwnerMockRulesVerificationView.as_view(),
        name="owner-mock-verify-rules",
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
