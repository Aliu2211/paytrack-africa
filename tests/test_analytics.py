import importlib.util
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
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


def _load_module(function_name):
    module_name = f"paytrack_{function_name}"
    spec = importlib.util.spec_from_file_location(module_name, FUNCTIONS_DIR / function_name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _stream_event(event_name, tenant_id, invoice_id, old_status=None, new_status=None, amount="1500.50"):
    def image(status):
        return {
            "tenant_id": {"S": tenant_id},
            "invoice_id": {"S": invoice_id},
            "status": {"S": status},
            "amount": {"N": amount},
        }

    record = {"eventName": event_name, "dynamodb": {}}
    if old_status:
        record["dynamodb"]["OldImage"] = image(old_status)
    if new_status:
        record["dynamodb"]["NewImage"] = image(new_status)
    return {"Records": [record]}


@pytest.fixture
def aws_resources():
    with mock_aws():
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["ANALYTICS_TABLE"] = "paytrack-analytics-test"
        os.environ["TENANTS_TABLE"] = "paytrack-tenants-test"
        os.environ["INVOICES_TABLE"] = "paytrack-invoices-test"
        os.environ["SES_SENDER_EMAIL"] = "sender@paytrack-test.africa"

        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=os.environ["ANALYTICS_TABLE"],
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "metric_key", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "metric_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
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
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        cognito_client = boto3.client("cognito-idp", region_name="us-east-1")
        pool = cognito_client.create_user_pool(
            PoolName="paytrack-test",
            Schema=[
                {"Name": "tenant_id", "AttributeDataType": "String", "Mutable": True},
                {"Name": "business_name", "AttributeDataType": "String", "Mutable": True},
            ],
        )
        os.environ["COGNITO_USER_POOL_ID"] = pool["UserPool"]["Id"]

        ses_client = boto3.client("ses", region_name="us-east-1")
        ses_client.verify_email_identity(EmailAddress=os.environ["SES_SENDER_EMAIL"])

        yield {
            "dynamodb": boto3.resource("dynamodb", region_name="us-east-1"),
            "cognito": cognito_client,
        }


@pytest.fixture
def analytics_module(aws_resources):
    return _load_module("analytics")


@pytest.fixture
def weekly_report_module(aws_resources):
    return _load_module("weekly_report")


def _analytics_value(dynamodb, tenant_id, metric_key):
    table = dynamodb.Table(os.environ["ANALYTICS_TABLE"])
    item = table.get_item(Key={"tenant_id": tenant_id, "metric_key": metric_key}).get("Item")
    return item["metric_value"] if item else Decimal(0)


def test_analytics_insert_increments_status_count(aws_resources, analytics_module):
    event = _stream_event("INSERT", TENANT_A, "INV-1", new_status="draft")
    analytics_module.lambda_handler(event, CONTEXT)

    assert _analytics_value(aws_resources["dynamodb"], TENANT_A, "invoices_draft") == 1


def test_analytics_status_change_moves_counter_and_tracks_outstanding(aws_resources, analytics_module):
    analytics_module.lambda_handler(_stream_event("INSERT", TENANT_A, "INV-1", new_status="draft"), CONTEXT)
    analytics_module.lambda_handler(
        _stream_event("MODIFY", TENANT_A, "INV-1", old_status="draft", new_status="sent"), CONTEXT
    )

    dynamodb = aws_resources["dynamodb"]
    assert _analytics_value(dynamodb, TENANT_A, "invoices_draft") == 0
    assert _analytics_value(dynamodb, TENANT_A, "invoices_sent") == 1
    assert _analytics_value(dynamodb, TENANT_A, "total_outstanding_amount") == Decimal("1500.50")


def test_analytics_paid_removes_outstanding_amount(aws_resources, analytics_module):
    analytics_module.lambda_handler(_stream_event("INSERT", TENANT_A, "INV-1", new_status="draft"), CONTEXT)
    analytics_module.lambda_handler(
        _stream_event("MODIFY", TENANT_A, "INV-1", old_status="draft", new_status="sent"), CONTEXT
    )
    analytics_module.lambda_handler(
        _stream_event("MODIFY", TENANT_A, "INV-1", old_status="sent", new_status="paid"), CONTEXT
    )

    dynamodb = aws_resources["dynamodb"]
    assert _analytics_value(dynamodb, TENANT_A, "invoices_sent") == 0
    assert _analytics_value(dynamodb, TENANT_A, "invoices_paid") == 1
    assert _analytics_value(dynamodb, TENANT_A, "total_outstanding_amount") == Decimal("0")


def test_analytics_status_unchanged_does_not_double_count(aws_resources, analytics_module):
    analytics_module.lambda_handler(_stream_event("INSERT", TENANT_A, "INV-1", new_status="sent"), CONTEXT)
    # A MODIFY that doesn't change status (e.g. description edited) should
    # be a no-op for the status counters.
    analytics_module.lambda_handler(
        _stream_event("MODIFY", TENANT_A, "INV-1", old_status="sent", new_status="sent"), CONTEXT
    )

    assert _analytics_value(aws_resources["dynamodb"], TENANT_A, "invoices_sent") == 1


def test_weekly_report_sends_summary_to_each_tenant(aws_resources, weekly_report_module):
    dynamodb = aws_resources["dynamodb"]
    now = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    today = date.today().isoformat()
    future_due = (date.today() + timedelta(days=10)).isoformat()
    past_due = (date.today() - timedelta(days=5)).isoformat()

    dynamodb.Table(os.environ["TENANTS_TABLE"]).put_item(Item={"tenant_id": TENANT_A})

    invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
    invoices_table.put_item(
        Item={
            "tenant_id": TENANT_A,
            "invoice_id": "INV-SENT-THIS-WEEK",
            "status": "sent",
            "updated_at": now,
            "due_date": future_due,
        }
    )
    invoices_table.put_item(
        Item={
            "tenant_id": TENANT_A,
            "invoice_id": "INV-PAID-THIS-WEEK",
            "status": "paid",
            "updated_at": now,
            "due_date": future_due,
        }
    )
    invoices_table.put_item(
        Item={
            "tenant_id": TENANT_A,
            "invoice_id": "INV-OVERDUE",
            "status": "sent",
            "updated_at": old,
            "due_date": past_due,
        }
    )

    dynamodb.Table(os.environ["ANALYTICS_TABLE"]).update_item(
        Key={"tenant_id": TENANT_A, "metric_key": "total_outstanding_amount"},
        UpdateExpression="ADD metric_value :v",
        ExpressionAttributeValues={":v": Decimal("3001.00")},
    )

    aws_resources["cognito"].admin_create_user(
        UserPoolId=os.environ["COGNITO_USER_POOL_ID"],
        Username="client@example.com",
        UserAttributes=[
            {"Name": "email", "Value": "client@example.com"},
            {"Name": "custom:tenant_id", "Value": TENANT_A},
            {"Name": "custom:business_name", "Value": "AgroVault Africa Ltd"},
        ],
        MessageAction="SUPPRESS",
    )

    summary = weekly_report_module.lambda_handler({}, CONTEXT)

    assert summary == {"tenants_processed": 1, "emails_sent": 1}
