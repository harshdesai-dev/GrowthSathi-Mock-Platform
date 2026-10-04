import yaml
from django.core.management import call_command


def _operation_ids(schema):
    return [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]


def test_openapi_schema_is_warning_free_and_owner_contracts_are_explicit(tmp_path):
    schema_path = tmp_path / "openapi.yml"
    call_command(
        "spectacular",
        validate=True,
        fail_on_warn=True,
        file=str(schema_path),
        verbosity=0,
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

    operation_ids = _operation_ids(schema)
    assert len(operation_ids) == len(set(operation_ids))

    expected_owner_operations = {
        "/api/v1/owner/mocks/": {"get": "owner_mocks_list"},
        "/api/v1/owner/mocks/{mock_id}/": {"get": "owner_mock_retrieve"},
        "/api/v1/owner/mocks/{mock_id}/questions/": {"get": "owner_mock_questions_list"},
        "/api/v1/owner/mocks/{mock_id}/questions/{question_id}/": {
            "get": "owner_mock_question_retrieve"
        },
        "/api/v1/owner/payments/": {"get": "owner_payments_list"},
        "/api/v1/owner/payments/{order_id}/": {"get": "owner_payment_retrieve"},
        "/api/v1/owner/students/": {"get": "owner_students_list"},
        "/api/v1/owner/students/{student_id}/": {"get": "owner_student_retrieve"},
    }
    for path, methods in expected_owner_operations.items():
        for method, operation_id in methods.items():
            operation = schema["paths"][path][method]
            assert operation["operationId"] == operation_id
            assert operation["responses"]["200"]["content"]["application/json"]["schema"]

    components = schema["components"]["schemas"]
    question_summary = components["OwnerQuestionSummary"]["properties"]
    question_option = components["OwnerQuestionOption"]["properties"]
    assert question_summary["question_preview"]["type"] == "string"
    assert question_summary["has_image"]["type"] == "boolean"
    assert question_option["has_image"]["type"] == "boolean"
    assert (
        components["OwnerQuestionImportCommitResponse"]["properties"]["imported_count"]["type"]
        == "integer"
    )

    assert "MockTestStatusEnum" in components
    assert "ResultCalculationRunStatusEnum" in components
    assert "Status741Enum" not in components
    assert "TargetEnum" not in components
