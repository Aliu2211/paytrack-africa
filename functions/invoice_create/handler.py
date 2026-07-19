import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
tenants_table = dynamodb.Table(os.environ["TENANTS_TABLE"])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUIRED_FIELDS = ["client_name", "client_email", "amount", "due_date"]


def _response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body, default=_decimal_default)}


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _next_invoice_number(tenant_id):
    # ADD on a numeric attribute upserts the tenant item and initializes the
    # counter at 0 if it doesn't exist yet, so no separate tenant-provisioning
    # step is required before the first invoice is created.
    result = tenants_table.update_item(
        Key={"tenant_id": tenant_id},
        UpdateExpression="ADD invoice_counter :incr",
        ExpressionAttributeValues={":incr": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["invoice_counter"])


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"]["custom:tenant_id"]
    logger.info(json.dumps({
        "event": "invoke_start", "function": "invoice_create",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    body = json.loads(event.get("body") or "{}", parse_float=Decimal)

    missing = [f for f in REQUIRED_FIELDS if body.get(f) in (None, "")]
    if missing:
        return _response(400, {"message": f"Missing required fields: {', '.join(missing)}"})

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    invoice_id = f"INV-{tenant_id[:8].upper()}-{uuid.uuid4().hex[:8].upper()}"
    invoice_number = _next_invoice_number(tenant_id)

    invoice = {
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "client_name": body["client_name"],
        "client_email": body["client_email"],
        "amount": body["amount"],
        "due_date": body["due_date"],
        "currency": body.get("currency", "GHS"),
        "description": body.get("description", ""),
        "line_items": body.get("line_items", []),
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }

    invoices_table.put_item(Item=invoice)

    logger.info(json.dumps({
        "event": "invoke_end", "function": "invoice_create",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    return _response(201, invoice)
