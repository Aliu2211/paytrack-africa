import base64
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body, default=_decimal_default)}


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _encode_key(key):
    if not key:
        return None
    return base64.b64encode(json.dumps(key, default=_decimal_default).encode()).decode()


def _decode_key(token):
    if not token:
        return None
    return json.loads(base64.b64decode(token.encode()).decode())


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"]["custom:tenant_id"]
    params = event.get("queryStringParameters") or {}

    status = params.get("status")
    due_before = params.get("due_before")
    due_after = params.get("due_after")

    try:
        limit = min(int(params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    query_kwargs = {"Limit": limit}

    exclusive_start_key = _decode_key(params.get("last_evaluated_key"))
    if exclusive_start_key:
        query_kwargs["ExclusiveStartKey"] = exclusive_start_key

    if due_before or due_after:
        key_condition = Key("tenant_id").eq(tenant_id)
        if due_before and due_after:
            key_condition &= Key("due_date").between(due_after, due_before)
        elif due_after:
            key_condition &= Key("due_date").gte(due_after)
        else:
            key_condition &= Key("due_date").lte(due_before)

        query_kwargs["IndexName"] = "status-due-date-index"
        query_kwargs["KeyConditionExpression"] = key_condition
    else:
        query_kwargs["KeyConditionExpression"] = Key("tenant_id").eq(tenant_id)

    if status:
        query_kwargs["FilterExpression"] = Attr("status").eq(status)

    result = invoices_table.query(**query_kwargs)

    return _response(200, {
        "invoices": result.get("Items", []),
        "count": result.get("Count", 0),
        "last_evaluated_key": _encode_key(result.get("LastEvaluatedKey")),
    })
