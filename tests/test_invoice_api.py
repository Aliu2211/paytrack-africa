import importlib.util
import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REPO_ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_DIR = REPO_ROOT / "functions"

TENANT_A = "11111111-aaaa-4aaa-8aaa-111111111111"
TENANT_B = "22222222-bbbb-4bbb-8bbb-222222222222"


class _FakeContext:
    aws_request_id = "test-request-id"


CONTEXT = _FakeContext()

VALID_PAYLOAD = {
    "client_name": "AgroVault Africa Ltd",
    "client_email": "billing@agrovault.africa",
    "amount": 1500.5,
    "due_date": "2026-08-01",
}


def _load_handler(function_name):
    module_name = f"paytrack_{function_name}"
    spec = importlib.util.spec_from_file_location(module_name, FUNCTIONS_DIR / function_name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.lambda_handler


def _event(tenant_id, body=None, path_params=None, query_params=None):
    return {
        "requestContext": {"authorizer": {"claims": {"custom:tenant_id": tenant_id}}},
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params,
        "queryStringParameters": query_params,
    }


@pytest.fixture
def dynamodb_tables():
    with mock_aws():
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["INVOICES_TABLE"] = "paytrack-invoices-test"
        os.environ["TENANTS_TABLE"] = "paytrack-tenants-test"
        os.environ["ENVIRONMENT"] = "test"

        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=os.environ["TENANTS_TABLE"],
            KeySchema=[{"AttributeName": "tenant_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "tenant_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=os.environ["INVOICES_TABLE"],
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "invoice_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "invoice_id", "AttributeType": "S"},
                {"AttributeName": "due_date", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-due-date-index",
                    "KeySchema": [
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                        {"AttributeName": "due_date", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@pytest.fixture
def create_invoice(dynamodb_tables):
    return _load_handler("invoice_create")


@pytest.fixture
def get_invoice(dynamodb_tables):
    return _load_handler("invoice_get")


@pytest.fixture
def list_invoices(dynamodb_tables):
    return _load_handler("invoice_list")


@pytest.fixture
def update_invoice(dynamodb_tables):
    return _load_handler("invoice_update")


def test_create_invoice_success(create_invoice):
    response = create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)
    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["invoice_id"].startswith("INV-")
    assert body["invoice_number"] == 1
    assert body["status"] == "draft"


def test_create_invoice_missing_amount(create_invoice):
    payload = dict(VALID_PAYLOAD)
    del payload["amount"]
    response = create_invoice(_event(TENANT_A, body=payload), CONTEXT)
    assert response["statusCode"] == 400


def test_create_invoice_missing_client_name(create_invoice):
    payload = dict(VALID_PAYLOAD)
    del payload["client_name"]
    response = create_invoice(_event(TENANT_A, body=payload), CONTEXT)
    assert response["statusCode"] == 400


def test_get_invoice_success(create_invoice, get_invoice):
    created = json.loads(create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)["body"])
    response = get_invoice(_event(TENANT_A, path_params={"id": created["invoice_id"]}), CONTEXT)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["invoice_id"] == created["invoice_id"]


def test_get_invoice_wrong_tenant(create_invoice, get_invoice):
    created = json.loads(create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)["body"])
    response = get_invoice(_event(TENANT_B, path_params={"id": created["invoice_id"]}), CONTEXT)
    assert response["statusCode"] == 403


def test_get_invoice_not_found(get_invoice):
    response = get_invoice(_event(TENANT_A, path_params={"id": "INV-NOTFOUND-0000"}), CONTEXT)
    assert response["statusCode"] == 404


def test_list_invoices_empty(list_invoices):
    response = list_invoices(_event(TENANT_A), CONTEXT)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"invoices": [], "count": 0, "last_evaluated_key": None}


def test_list_invoices_own_tenant_only(create_invoice, list_invoices):
    create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)
    create_invoice(_event(TENANT_B, body=VALID_PAYLOAD), CONTEXT)
    response = list_invoices(_event(TENANT_A), CONTEXT)
    body = json.loads(response["body"])
    assert body["count"] == 1
    assert body["invoices"][0]["tenant_id"] == TENANT_A


def test_list_invoices_pagination(create_invoice, list_invoices):
    for _ in range(25):
        create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)
    response = list_invoices(_event(TENANT_A, query_params={"limit": "10"}), CONTEXT)
    body = json.loads(response["body"])
    assert body["count"] == 10
    assert body["last_evaluated_key"] is not None


def test_update_status_draft_to_sent(create_invoice, update_invoice):
    created = json.loads(create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)["body"])
    response = update_invoice(
        _event(TENANT_A, body={"status": "sent"}, path_params={"id": created["invoice_id"]}), CONTEXT
    )
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["status"] == "sent"


def test_update_status_invalid_transition(create_invoice, update_invoice):
    created = json.loads(create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)["body"])
    update_invoice(_event(TENANT_A, body={"status": "sent"}, path_params={"id": created["invoice_id"]}), CONTEXT)
    response = update_invoice(
        _event(TENANT_A, body={"status": "draft"}, path_params={"id": created["invoice_id"]}), CONTEXT
    )
    assert response["statusCode"] == 400


def test_update_wrong_tenant(create_invoice, update_invoice):
    created = json.loads(create_invoice(_event(TENANT_A, body=VALID_PAYLOAD), CONTEXT)["body"])
    response = update_invoice(
        _event(TENANT_B, body={"status": "sent"}, path_params={"id": created["invoice_id"]}), CONTEXT
    )
    assert response["statusCode"] == 403
