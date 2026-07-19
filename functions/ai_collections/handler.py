import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from google import genai

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
secretsmanager = boto3.client("secretsmanager")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GEMINI_SECRET_ARN = os.environ["GEMINI_SECRET_ARN"]
GEMINI_MODEL = "gemini-flash-latest"

TONE_BY_DAYS_OVERDUE = [
    (14, "firm but polite"),
    (30, "urgent"),
    (None, "final notice"),
]


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
        "body": json.dumps(body, default=_decimal_default),
    }


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _tone_for(days_overdue):
    for threshold, tone in TONE_BY_DAYS_OVERDUE:
        if threshold is None or days_overdue < threshold:
            return tone


def _gemini_api_key():
    secret = secretsmanager.get_secret_value(SecretId=GEMINI_SECRET_ARN)
    return json.loads(secret["SecretString"])["api_key"]


def _generate_collections_message(invoice, days_overdue, tone):
    # Isolated so tests can monkeypatch this single call point instead of
    # mocking the Gemini SDK -- unit tests should verify our tone-selection
    # logic, not make a real network call or assert on the model's exact prose.
    client = genai.Client(api_key=_gemini_api_key())
    prompt = (
        f"Write a {tone} payment collections message to {invoice['client_name']} for invoice "
        f"{invoice['invoice_number']}, amount {invoice.get('currency', 'GHS')} {invoice['amount']}, "
        f"{days_overdue} days overdue. Maximum 3 sentences, professional English."
    )
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text.strip()


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"].get("custom:tenant_id")
    if not tenant_id:
        return _response(403, {"message": "No tenant assigned to this account. Contact your administrator."})
    invoice_id = event["pathParameters"]["id"]
    logger.info(json.dumps({
        "event": "invoke_start", "function": "ai_collections",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))

    invoice = invoices_table.get_item(Key={"tenant_id": tenant_id, "invoice_id": invoice_id}).get("Item")
    if not invoice:
        scan = invoices_table.scan(FilterExpression=Attr("invoice_id").eq(invoice_id))
        if scan.get("Items"):
            return _response(403, {"message": "Forbidden"})
        return _response(404, {"message": "Invoice not found"})

    due_date = datetime.strptime(invoice["due_date"], "%Y-%m-%d").date()
    days_overdue = (date.today() - due_date).days
    tone = _tone_for(days_overdue)

    message = _generate_collections_message(invoice, days_overdue, tone)

    invoices_table.update_item(
        Key={"tenant_id": tenant_id, "invoice_id": invoice_id},
        UpdateExpression="SET last_collections_message = :message",
        ExpressionAttributeValues={":message": message},
    )

    logger.info(json.dumps({
        "event": "invoke_end", "function": "ai_collections",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    return _response(200, {"invoice_id": invoice_id, "days_overdue": days_overdue, "message": message})
