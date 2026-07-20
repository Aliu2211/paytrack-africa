import json
import logging
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource("dynamodb")
analytics_table = dynamodb.Table(os.environ["ANALYTICS_TABLE"])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_deserializer = TypeDeserializer()


def _deserialize(image):
    if not image:
        return None
    return {key: _deserializer.deserialize(value) for key, value in image.items()}


def _adjust_counter(tenant_id, metric_key, delta):
    analytics_table.update_item(
        Key={"tenant_id": tenant_id, "metric_key": metric_key},
        UpdateExpression="ADD metric_value :delta",
        ExpressionAttributeValues={":delta": delta},
    )


def lambda_handler(event, context):
    records_processed = 0

    for record in event.get("Records", []):
        new_image = _deserialize(record["dynamodb"].get("NewImage"))
        old_image = _deserialize(record["dynamodb"].get("OldImage"))

        tenant_id = (new_image or old_image or {}).get("tenant_id")
        if not tenant_id:
            continue

        old_status = old_image.get("status") if old_image else None
        new_status = new_image.get("status") if new_image else None

        # Covers INSERT (old_status is None), REMOVE (new_status is None),
        # and MODIFY with a status change. A MODIFY that leaves status
        # unchanged skips both branches -- no double counting.
        if old_status and old_status != new_status:
            _adjust_counter(tenant_id, f"invoices_{old_status}", -1)
            if old_status == "sent" and old_image and "amount" in old_image:
                _adjust_counter(tenant_id, "total_outstanding_amount", -old_image["amount"])

        if new_status and new_status != old_status:
            _adjust_counter(tenant_id, f"invoices_{new_status}", 1)
            if new_status == "sent" and new_image and "amount" in new_image:
                _adjust_counter(tenant_id, "total_outstanding_amount", new_image["amount"])

        records_processed += 1

    summary = {"records_processed": records_processed}
    logger.info(json.dumps({"event": "invoke_end", "function": "analytics", **summary}))
    return summary
