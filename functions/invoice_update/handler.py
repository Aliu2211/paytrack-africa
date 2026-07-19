import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

IMMUTABLE_FIELDS = {"tenant_id", "invoice_id", "created_at"}

VALID_TRANSITIONS = {
    ("draft", "sent"),
    ("draft", "cancelled"),
    ("sent", "paid"),
}


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


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"]["custom:tenant_id"]
    invoice_id = event["pathParameters"]["id"]
    logger.info(json.dumps({
        "event": "invoke_start", "function": "invoice_update",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    body = json.loads(event.get("body") or "{}", parse_float=Decimal)

    existing = invoices_table.get_item(Key={"tenant_id": tenant_id, "invoice_id": invoice_id}).get("Item")
    if not existing:
        # Not found under the caller's tenant -- check whether it exists for
        # another tenant so 403 (wrong tenant) can be distinguished from 404.
        scan = invoices_table.scan(FilterExpression=Attr("invoice_id").eq(invoice_id))
        if scan.get("Items"):
            return _response(403, {"message": "Forbidden"})
        return _response(404, {"message": "Invoice not found"})

    rejected = IMMUTABLE_FIELDS & set(body.keys())
    if rejected:
        return _response(400, {"message": f"Cannot update fields: {', '.join(sorted(rejected))}"})

    if "status" in body:
        transition = (existing["status"], body["status"])
        if transition not in VALID_TRANSITIONS:
            return _response(400, {
                "message": f"Invalid status transition: {existing['status']} -> {body['status']}"
            })

    updates = dict(body)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Placeholder names/values use an "upd" prefix, distinct from the "#nN"/":vN"
    # placeholders boto3 auto-generates for the ConditionExpression Attr object
    # below -- a shared prefix would silently collide and clobber values.
    expression_names = {}
    expression_values = {}
    set_clauses = []
    for i, (key, value) in enumerate(updates.items()):
        name_placeholder = f"#upd{i}"
        value_placeholder = f":upd{i}"
        set_clauses.append(f"{name_placeholder} = {value_placeholder}")
        expression_names[name_placeholder] = key
        expression_values[value_placeholder] = value

    try:
        result = invoices_table.update_item(
            Key={"tenant_id": tenant_id, "invoice_id": invoice_id},
            UpdateExpression="SET " + ", ".join(set_clauses),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
            ConditionExpression=Attr("tenant_id").eq(tenant_id),
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(403, {"message": "Forbidden"})
        raise

    logger.info(json.dumps({
        "event": "invoke_end", "function": "invoice_update",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    return _response(200, result["Attributes"])
