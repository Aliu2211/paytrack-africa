import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
    tenant_id = event["requestContext"]["authorizer"]["claims"].get("custom:tenant_id")
    if not tenant_id:
        return _response(403, {"message": "No tenant assigned to this account. Contact your administrator."})
    invoice_id = event["pathParameters"]["id"]
    logger.info(json.dumps({
        "event": "invoke_start", "function": "invoice_get",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))

    item = invoices_table.get_item(Key={"tenant_id": tenant_id, "invoice_id": invoice_id}).get("Item")

    logger.info(json.dumps({
        "event": "invoke_end", "function": "invoice_get",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))

    if item:
        return _response(200, item)

    # Not found under the caller's tenant -- check whether it exists for
    # another tenant so 403 (wrong tenant) can be distinguished from 404.
    scan = invoices_table.scan(FilterExpression=Attr("invoice_id").eq(invoice_id))
    if scan.get("Items"):
        return _response(403, {"message": "Forbidden"})

    return _response(404, {"message": "Invoice not found"})
