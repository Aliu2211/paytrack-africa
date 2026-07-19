import importlib.util
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REPO_ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_DIR = REPO_ROOT / "functions"

TENANT_A = "11111111-aaaa-4aaa-8aaa-111111111111"


class _FakeContext:
    aws_request_id = "test-request-id"


CONTEXT = _FakeContext()

SNS_TOPIC_NAME = "paytrack-payment-reminders-test"
SES_SENDER_EMAIL = "sender@paytrack-test.africa"
PDF_BUCKET_NAME = "paytrack-invoices-pdf-test"
GEMINI_SECRET_NAME = "paytrack/gemini-api-key"


def _load_module(function_name):
    module_name = f"paytrack_{function_name}"
    spec = importlib.util.spec_from_file_location(module_name, FUNCTIONS_DIR / function_name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _event(tenant_id, path_params=None):
    return {
        "requestContext": {"authorizer": {"claims": {"custom:tenant_id": tenant_id}}},
        "pathParameters": path_params,
    }


def _seed_invoice(invoices_table, invoice_id, due_date, status, **overrides):
    item = {
        "tenant_id": TENANT_A,
        "invoice_id": invoice_id,
        "invoice_number": 1,
        "client_name": "AgroVault Africa Ltd",
        "client_email": SES_SENDER_EMAIL,
        "amount": Decimal("1500.50"),
        "currency": "GHS",
        "due_date": due_date,
        "status": status,
    }
    item.update(overrides)
    invoices_table.put_item(Item=item)
    return item


@pytest.fixture
def aws_resources():
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

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.Table(os.environ["TENANTS_TABLE"]).put_item(Item={"tenant_id": TENANT_A})

        sns_client = boto3.client("sns", region_name="us-east-1")
        os.environ["SNS_TOPIC_ARN"] = sns_client.create_topic(Name=SNS_TOPIC_NAME)["TopicArn"]
        os.environ["SES_SENDER_EMAIL"] = SES_SENDER_EMAIL

        ses_client = boto3.client("ses", region_name="us-east-1")
        ses_client.verify_email_identity(EmailAddress=SES_SENDER_EMAIL)

        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket=PDF_BUCKET_NAME)
        os.environ["PDF_BUCKET_NAME"] = PDF_BUCKET_NAME

        secrets_client = boto3.client("secretsmanager", region_name="us-east-1")
        secret = secrets_client.create_secret(
            Name=GEMINI_SECRET_NAME, SecretString=json.dumps({"api_key": "test-fake-key"})
        )
        os.environ["GEMINI_SECRET_ARN"] = secret["ARN"]

        yield dynamodb.Table(os.environ["INVOICES_TABLE"])


@pytest.fixture
def payment_reminder(aws_resources):
    return _load_module("payment_reminder")


@pytest.fixture
def invoice_pdf_module(aws_resources):
    return _load_module("invoice_pdf")


@pytest.fixture
def ai_collections_module(aws_resources):
    return _load_module("ai_collections")


def test_reminder_scans_correct_invoices(aws_resources, payment_reminder):
    invoices_table = aws_resources
    today = date.today()
    _seed_invoice(invoices_table, "INV-DUE-SOON", (today + timedelta(days=2)).isoformat(), "sent")
    _seed_invoice(invoices_table, "INV-DUE-LATER", (today + timedelta(days=10)).isoformat(), "sent")

    summary = payment_reminder.lambda_handler({}, CONTEXT)

    assert summary["total_reminded"] == 1
    assert summary["reminded_invoice_ids"] == ["INV-DUE-SOON"]


def test_reminder_skips_paid_invoices(aws_resources, payment_reminder):
    invoices_table = aws_resources
    today = date.today()
    _seed_invoice(invoices_table, "INV-PAID", (today + timedelta(days=2)).isoformat(), "paid")

    summary = payment_reminder.lambda_handler({}, CONTEXT)

    assert summary["total_reminded"] == 0
    assert "INV-PAID" not in summary["reminded_invoice_ids"]


def test_reminder_skips_draft_invoices(aws_resources, payment_reminder):
    invoices_table = aws_resources
    today = date.today()
    _seed_invoice(invoices_table, "INV-DRAFT", (today + timedelta(days=2)).isoformat(), "draft")

    summary = payment_reminder.lambda_handler({}, CONTEXT)

    assert summary["total_reminded"] == 0
    assert "INV-DRAFT" not in summary["reminded_invoice_ids"]


def test_pdf_generates_and_uploads(aws_resources, invoice_pdf_module):
    invoices_table = aws_resources
    due_date = (date.today() + timedelta(days=30)).isoformat()
    invoice = _seed_invoice(invoices_table, "INV-PDF-TEST", due_date, "sent")

    response = invoice_pdf_module.lambda_handler(
        _event(TENANT_A, path_params={"id": invoice["invoice_id"]}), CONTEXT
    )

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["expires_in"] == 86400
    assert body["pdf_url"]

    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.head_object(Bucket=PDF_BUCKET_NAME, Key=f"{TENANT_A}/{invoice['invoice_id']}.pdf")


def test_collections_message_low_urgency(aws_resources, ai_collections_module, monkeypatch):
    invoices_table = aws_resources
    due_date = (date.today() - timedelta(days=5)).isoformat()
    invoice = _seed_invoice(invoices_table, "INV-LOW-URGENCY", due_date, "sent")

    monkeypatch.setattr(
        ai_collections_module,
        "_generate_collections_message",
        lambda invoice, days_overdue, tone: f"[{tone}] reminder for {invoice['client_name']}",
    )

    response = ai_collections_module.lambda_handler(
        _event(TENANT_A, path_params={"id": invoice["invoice_id"]}), CONTEXT
    )

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["days_overdue"] == 5
    assert "firm but polite" in body["message"]


def test_collections_message_high_urgency(aws_resources, ai_collections_module, monkeypatch):
    invoices_table = aws_resources
    due_date = (date.today() - timedelta(days=45)).isoformat()
    invoice = _seed_invoice(invoices_table, "INV-HIGH-URGENCY", due_date, "sent")

    monkeypatch.setattr(
        ai_collections_module,
        "_generate_collections_message",
        lambda invoice, days_overdue, tone: f"[{tone}] reminder for {invoice['client_name']}",
    )

    response = ai_collections_module.lambda_handler(
        _event(TENANT_A, path_params={"id": invoice["invoice_id"]}), CONTEXT
    )

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["days_overdue"] == 45
    assert "final notice" in body["message"]
