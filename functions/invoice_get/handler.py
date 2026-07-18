import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])


def _response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body, default=_decimal_default)}


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"]["custom:tenant_id"]
    invoice_id = event["pathParameters"]["id"]

    item = invoices_table.get_item(Key={"tenant_id": tenant_id, "invoice_id": invoice_id}).get("Item")
    if item:
        return _response(200, item)

    # Not found under the caller's tenant -- check whether it exists for
    # another tenant so 403 (wrong tenant) can be distinguished from 404.
    scan = invoices_table.scan(FilterExpression=Attr("invoice_id").eq(invoice_id))
    if scan.get("Items"):
        return _response(403, {"message": "Forbidden"})

    return _response(404, {"message": "Invoice not found"})
