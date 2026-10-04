"""Owner operations backed exclusively by the existing domain services."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.owner_mocks import owner_mock_detail_queryset
from apps.attempts.models import Attempt
from apps.commerce.models import MockAccessGrant, Order, Payment
from apps.commerce.services import reconcile_gateway_order, reconcile_gateway_payment
from apps.common.throttles import ReadThrottle
from apps.exams.models import MockTest
from apps.exams.services import correct_answer_key, transition_mock
from apps.results.models import ResultCalculationRun
from apps.results.services import (
    calculate_results,
    publish_results,
    reconcile_for_results,
    verify_answer_key,
)

from .permissions import IsActiveOwner
from .serializers import OwnerMockDetailSerializer


def _raise_api_validation(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError({"non_field_errors": exc.messages}) from exc


def _run_data(run):
    if not run:
        return None
    return {
        "id": run.pk,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "key_verified_at": run.key_verified_at,
        "participant_count": run.participant_count,
        "excluded_attempt_count": len(run.excluded_attempts),
        "notes": run.notes,
        "errors": run.errors,
        "published_at": run.published_at,
    }


def _result_mock_data(mock, *, runs=None):
    runs = list(runs if runs is not None else mock.result_runs.all())
    latest = runs[0] if runs else None
    warnings = []
    if mock.status not in {MockTest.Status.CLOSED, MockTest.Status.RESULTS_PUBLISHED}:
        warnings.append("Close the mock before starting result operations.")
    if not latest:
        warnings.append("The answer key has not been verified for a result batch.")
    elif latest.status in {
        ResultCalculationRun.Status.INVALIDATED,
        ResultCalculationRun.Status.FAILED,
    }:
        warnings.append(latest.errors or "The latest result batch cannot be published.")
    run_status = latest.status if latest else None
    calculation_state = (
        "COMPLETE"
        if run_status
        in {ResultCalculationRun.Status.COMPLETE, ResultCalculationRun.Status.PUBLISHED}
        else run_status or "NOT_STARTED"
    )
    verification_state = (
        "VERIFIED"
        if run_status
        in {
            ResultCalculationRun.Status.VERIFIED,
            ResultCalculationRun.Status.CALCULATING,
            ResultCalculationRun.Status.COMPLETE,
            ResultCalculationRun.Status.PUBLISHED,
        }
        else "REQUIRED"
    )
    publication_state = (
        "PUBLISHED"
        if run_status == ResultCalculationRun.Status.PUBLISHED
        else "READY"
        if run_status == ResultCalculationRun.Status.COMPLETE
        else "NOT_READY"
    )
    return {
        "id": mock.pk,
        "title": mock.title,
        "status": mock.status,
        "attempt_count": mock.attempt_count,
        "result_release_at": mock.result_release_at,
        "calculation_state": calculation_state,
        "verification_state": verification_state,
        "publication_state": publication_state,
        "latest_run": _run_data(latest),
        "operational_warnings": warnings,
        "runs": [_run_data(run) for run in runs],
    }


class OwnerPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class OwnerLifecycleInputSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=MockTest.Status.choices)
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class OwnerMockTransitionView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_mock_transition",
        request=OwnerLifecycleInputSerializer,
        responses={200: OwnerMockDetailSerializer},
    )
    def post(self, request, mock_id):
        serializer = OwnerLifecycleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transition_mock(
                mock_id,
                serializer.validated_data["target"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        mock = get_object_or_404(owner_mock_detail_queryset(), pk=mock_id)
        return Response(OwnerMockDetailSerializer(mock).data)


class OwnerResultNotesSerializer(serializers.Serializer):
    notes = serializers.CharField(trim_whitespace=True)
    confirmed = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs["confirmed"]:
            raise serializers.ValidationError({"confirmed": "Explicit confirmation is required."})
        return attrs


class OwnerResultConfirmationSerializer(serializers.Serializer):
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class OwnerAnswerCorrectionSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    reason = serializers.CharField(trim_whitespace=True)
    correct_option = serializers.ChoiceField(choices=tuple("ABCD"), required=False)
    numeric_answer = serializers.DecimalField(
        max_digits=18, decimal_places=8, required=False, allow_null=True
    )
    numeric_tolerance = serializers.DecimalField(
        max_digits=18, decimal_places=8, required=False, allow_null=True
    )
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class OwnerResultRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=ResultCalculationRun.Status.choices)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    key_verified_at = serializers.DateTimeField()
    participant_count = serializers.IntegerField(min_value=0)
    excluded_attempt_count = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(allow_blank=True)
    errors = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)


class OwnerResultMockSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    status = serializers.ChoiceField(choices=MockTest.Status.choices)
    attempt_count = serializers.IntegerField(min_value=0)
    result_release_at = serializers.DateTimeField()
    calculation_state = serializers.ChoiceField(
        choices=(
            "NOT_STARTED",
            "VERIFIED",
            "CALCULATING",
            "COMPLETE",
            "INVALIDATED",
            "WITHDRAWN",
            "FAILED",
        )
    )
    verification_state = serializers.ChoiceField(choices=("REQUIRED", "VERIFIED"))
    publication_state = serializers.ChoiceField(choices=("NOT_READY", "READY", "PUBLISHED"))
    latest_run = OwnerResultRunSerializer(allow_null=True)
    operational_warnings = serializers.ListField(child=serializers.CharField())
    runs = OwnerResultRunSerializer(many=True)


class OwnerResultsResponseSerializer(serializers.Serializer):
    results = OwnerResultMockSerializer(many=True)


class OwnerResultSearchSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)


class OwnerExcludedAttemptSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField()
    status = serializers.CharField()
    reason = serializers.CharField()


class OwnerResultReconcileResponseSerializer(serializers.Serializer):
    participant_count = serializers.IntegerField(min_value=0)
    excluded_attempts = OwnerExcludedAttemptSerializer(many=True)


class OwnerAnswerCorrectionResponseSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    corrected = serializers.BooleanField()


class OwnerPaginationQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class OwnerStudentQuerySerializer(OwnerPaginationQuerySerializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)


class OwnerStudentSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(allow_blank=True)
    class_level = serializers.CharField(allow_blank=True)
    exam_target = serializers.CharField(allow_blank=True)
    onboarding_completed = serializers.BooleanField()
    joined_at = serializers.DateTimeField()
    purchased_mocks_count = serializers.IntegerField(min_value=0)
    attempts_count = serializers.IntegerField(min_value=0)


class OwnerStudentOrderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    offer = serializers.CharField()
    amount_paise = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=Order.Status.choices)
    created_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)


class OwnerStudentAccessSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mock_id = serializers.UUIDField()
    mock_title = serializers.CharField()
    status = serializers.ChoiceField(choices=MockAccessGrant.Status.choices)
    granted_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)


class OwnerStudentResultSerializer(serializers.Serializer):
    score = serializers.FloatField()
    rank = serializers.IntegerField(min_value=1)
    percentile = serializers.FloatField(min_value=0, max_value=100)
    published_at = serializers.DateTimeField()


class OwnerStudentAttemptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mock_id = serializers.UUIDField()
    mock_title = serializers.CharField()
    status = serializers.ChoiceField(choices=Attempt.Status.choices)
    started_at = serializers.DateTimeField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    result = OwnerStudentResultSerializer(allow_null=True)


class OwnerStudentDetailSerializer(OwnerStudentSummarySerializer):
    orders = OwnerStudentOrderSerializer(many=True)
    access = OwnerStudentAccessSerializer(many=True)
    attempts = OwnerStudentAttemptSerializer(many=True)


class OwnerStudentPageSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OwnerStudentSummarySerializer(many=True)


class OwnerPaymentQuerySerializer(OwnerPaginationQuerySerializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    order_status = serializers.ChoiceField(choices=Order.Status.choices, required=False)
    payment_status = serializers.ChoiceField(choices=Payment.Status.choices, required=False)


class OwnerOrderStudentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(allow_blank=True)
    email = serializers.EmailField()


class OwnerOrderSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    student = OwnerOrderStudentSerializer()
    offer = serializers.CharField()
    amount_paise = serializers.IntegerField(min_value=0)
    currency = serializers.CharField(max_length=3)
    order_status = serializers.ChoiceField(choices=Order.Status.choices)
    payment_status = serializers.ChoiceField(
        choices=Payment.Status.choices,
        allow_null=True,
    )
    created_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    review_required = serializers.BooleanField()
    review_note = serializers.CharField(allow_blank=True)
    gateway_order_id = serializers.CharField(allow_blank=True, allow_null=True)


class OwnerPaymentAttemptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    gateway_payment_id = serializers.CharField()
    amount_paise = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=Payment.Status.choices)
    created_at = serializers.DateTimeField()


class OwnerPaymentAccessGrantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mock_id = serializers.UUIDField()
    mock_title = serializers.CharField()
    status = serializers.ChoiceField(choices=MockAccessGrant.Status.choices)
    granted_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)


class OwnerPaymentDetailSerializer(OwnerOrderSummarySerializer):
    payments = OwnerPaymentAttemptSerializer(many=True)
    access_grants = OwnerPaymentAccessGrantSerializer(many=True)
    reconciliation_state = serializers.ChoiceField(
        choices=("REVIEW_REQUIRED", "NO_REVIEW_REQUIRED")
    )


class OwnerPaymentPageSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OwnerOrderSummarySerializer(many=True)


def _result_queryset():
    runs = ResultCalculationRun.objects.defer("paper_snapshot").order_by("-started_at", "id")
    return (
        MockTest.objects.filter(
            status__in=[MockTest.Status.CLOSED, MockTest.Status.RESULTS_PUBLISHED]
        )
        .annotate(attempt_count=Count("attempts", distinct=True))
        .prefetch_related(Prefetch("result_runs", queryset=runs))
        .order_by("-ends_at", "title")
    )


class OwnerResultsView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_results_list",
        parameters=[OwnerResultSearchSerializer],
        responses={200: OwnerResultsResponseSerializer},
    )
    def get(self, request):
        mocks = _result_queryset()
        search = request.query_params.get("search", "").strip()
        if search:
            mocks = mocks.filter(title__icontains=search)
        return Response({"results": [_result_mock_data(mock) for mock in mocks]})


class OwnerMockResultsView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_mock_results_retrieve",
        responses={200: OwnerResultMockSerializer},
    )
    def get(self, request, mock_id):
        mock = get_object_or_404(_result_queryset(), pk=mock_id)
        return Response(_result_mock_data(mock))


class OwnerResultReconcileView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_result_attempts_reconcile",
        request=OwnerResultConfirmationSerializer,
        responses={200: OwnerResultReconcileResponseSerializer},
    )
    def post(self, request, mock_id):
        serializer = OwnerResultConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            outcome = reconcile_for_results(mock_id, actor=request.user)
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(outcome)


class OwnerResultVerifyView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_result_answer_key_verify",
        request=OwnerResultNotesSerializer,
        responses={200: OwnerResultRunSerializer},
    )
    def post(self, request, mock_id):
        serializer = OwnerResultNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = verify_answer_key(
                mock_id,
                actor=request.user,
                notes=serializer.validated_data["notes"],
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(_run_data(run))


class OwnerResultCalculateView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_result_calculate",
        request=OwnerResultConfirmationSerializer,
        responses={200: OwnerResultRunSerializer},
    )
    def post(self, request, mock_id, run_id):
        serializer = OwnerResultConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(ResultCalculationRun, pk=run_id, mock_test_id=mock_id)
        try:
            run = calculate_results(run_id, actor=request.user)
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(_run_data(run))


class OwnerResultPublishView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_result_publish",
        request=OwnerResultConfirmationSerializer,
        responses={200: OwnerResultRunSerializer},
    )
    def post(self, request, mock_id, run_id):
        serializer = OwnerResultConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(ResultCalculationRun, pk=run_id, mock_test_id=mock_id)
        try:
            run = publish_results(run_id, actor=request.user)
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(_run_data(run))


class OwnerAnswerCorrectionView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_result_answer_correct",
        request=OwnerAnswerCorrectionSerializer,
        responses={200: OwnerAnswerCorrectionResponseSerializer},
    )
    def post(self, request, mock_id):
        serializer = OwnerAnswerCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_id = serializer.validated_data.pop("question_id")
        serializer.validated_data.pop("confirmed")
        get_object_or_404(MockTest, pk=mock_id, questions__pk=question_id)
        try:
            question = correct_answer_key(
                question_id,
                actor=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response({"question_id": question.pk, "corrected": True})


def _student_queryset():
    return (
        User.objects.filter(is_staff=False, is_superuser=False)
        .select_related("profile")
        .annotate(
            purchased_mocks_count=Count(
                "orders__items__mock_test",
                filter=Q(orders__status=Order.Status.PAID),
                distinct=True,
            ),
            attempts_count=Count("attempts", distinct=True),
        )
        .order_by("-created_at", "pk")
    )


def _student_summary(user):
    profile = user.profile
    return {
        "id": user.pk,
        "name": profile.full_name or user.get_full_name(),
        "email": user.email,
        "phone": profile.phone,
        "class_level": profile.class_level,
        "exam_target": profile.target_exam,
        "onboarding_completed": profile.onboarding_completed,
        "joined_at": user.created_at,
        "purchased_mocks_count": user.purchased_mocks_count,
        "attempts_count": user.attempts_count,
    }


class OwnerStudentsView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_students_list",
        parameters=[OwnerStudentQuerySerializer],
        responses={200: OwnerStudentPageSerializer},
    )
    def get(self, request):
        queryset = _student_queryset()
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(profile__full_name__icontains=search)
                | Q(profile__phone__icontains=search)
            )
        paginator = OwnerPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([_student_summary(user) for user in page])


class OwnerStudentDetailView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_student_retrieve",
        responses={200: OwnerStudentDetailSerializer},
    )
    def get(self, request, student_id):
        user = get_object_or_404(_student_queryset(), pk=student_id)
        orders = user.orders.select_related("offer").order_by("-created_at")
        grants = user.mock_access.select_related("mock_test", "source_order_item").order_by(
            "-granted_at"
        )
        attempts = (
            Attempt.objects.filter(student=user)
            .select_related("mock_test", "result")
            .order_by("-started_at")
        )
        return Response(
            {
                **_student_summary(user),
                "orders": [
                    {
                        "id": order.pk,
                        "offer": order.offer_name_snapshot,
                        "amount_paise": order.total_amount_paise,
                        "status": order.status,
                        "created_at": order.created_at,
                        "paid_at": order.paid_at,
                    }
                    for order in orders
                ],
                "access": [
                    {
                        "id": grant.pk,
                        "mock_id": grant.mock_test_id,
                        "mock_title": grant.mock_test.title,
                        "status": grant.status,
                        "granted_at": grant.granted_at,
                        "revoked_at": grant.revoked_at,
                    }
                    for grant in grants
                ],
                "attempts": [
                    {
                        "id": attempt.pk,
                        "mock_id": attempt.mock_test_id,
                        "mock_title": attempt.mock_test.title,
                        "status": attempt.status,
                        "started_at": attempt.started_at,
                        "submitted_at": attempt.submitted_at,
                        "result": (
                            {
                                "score": attempt.result.score,
                                "rank": attempt.result.rank,
                                "percentile": attempt.result.percentile,
                                "published_at": attempt.result.published_at,
                            }
                            if hasattr(attempt, "result")
                            else None
                        ),
                    }
                    for attempt in attempts
                ],
            }
        )


def _payment_queryset():
    payments = Payment.objects.only(
        "id", "order_id", "gateway_payment_id", "amount_paise", "status", "created_at"
    ).order_by("-created_at")
    return (
        Order.objects.select_related("student", "student__profile", "offer")
        .prefetch_related(Prefetch("payments", queryset=payments))
        .order_by("-created_at", "pk")
    )


def _order_summary(order):
    payment_rows = list(order.payments.all())
    return {
        "id": order.pk,
        "student": {
            "id": order.student_id,
            "name": order.student.profile.full_name or order.student.get_full_name(),
            "email": order.student.email,
        },
        "offer": order.offer_name_snapshot,
        "amount_paise": order.total_amount_paise,
        "currency": order.currency,
        "order_status": order.status,
        "payment_status": payment_rows[0].status if payment_rows else None,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "review_required": order.review_required,
        "review_note": order.review_note,
        "gateway_order_id": order.gateway_order_id,
    }


class OwnerPaymentsView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_payments_list",
        parameters=[OwnerPaymentQuerySerializer],
        responses={200: OwnerPaymentPageSerializer},
    )
    def get(self, request):
        queryset = _payment_queryset()
        order_status = request.query_params.get("order_status", "")
        payment_status = request.query_params.get("payment_status", "")
        search = request.query_params.get("search", "").strip()
        if order_status:
            queryset = queryset.filter(status=order_status)
        if payment_status:
            queryset = queryset.filter(payments__status=payment_status).distinct()
        if search:
            queryset = queryset.filter(
                Q(id__icontains=search)
                | Q(gateway_order_id__icontains=search)
                | Q(student__email__icontains=search)
                | Q(student__profile__full_name__icontains=search)
            )
        paginator = OwnerPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([_order_summary(order) for order in page])


class OwnerPaymentDetailView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_payment_retrieve",
        responses={200: OwnerPaymentDetailSerializer},
    )
    def get(self, request, order_id):
        order = get_object_or_404(_payment_queryset(), pk=order_id)
        grants = MockAccessGrant.objects.filter(source_order_item__order=order).select_related(
            "mock_test"
        )
        return Response(
            {
                **_order_summary(order),
                "payments": [
                    {
                        "id": payment.pk,
                        "gateway_payment_id": payment.gateway_payment_id,
                        "amount_paise": payment.amount_paise,
                        "status": payment.status,
                        "created_at": payment.created_at,
                    }
                    for payment in order.payments.all()
                ],
                "access_grants": [
                    {
                        "id": grant.pk,
                        "mock_id": grant.mock_test_id,
                        "mock_title": grant.mock_test.title,
                        "status": grant.status,
                        "granted_at": grant.granted_at,
                        "revoked_at": grant.revoked_at,
                    }
                    for grant in grants
                ],
                "reconciliation_state": (
                    "REVIEW_REQUIRED" if order.review_required else "NO_REVIEW_REQUIRED"
                ),
            }
        )


class OwnerPaymentReconcileSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("ORDER", "PAYMENT"))
    reference = serializers.CharField(trim_whitespace=True, max_length=100)
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class OwnerPaymentReconcileView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        operation_id="owner_payment_reconcile",
        request=OwnerPaymentReconcileSerializer,
        responses={200: OwnerOrderSummarySerializer},
    )
    def post(self, request, order_id):
        serializer = OwnerPaymentReconcileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            if data["kind"] == "ORDER":
                order = reconcile_gateway_order(order_id, data["reference"], actor=request.user)
            else:
                order = reconcile_gateway_payment(order_id, data["reference"], actor=request.user)
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        refreshed = get_object_or_404(_payment_queryset(), pk=order.pk)
        return Response(_order_summary(refreshed), status=status.HTTP_200_OK)
