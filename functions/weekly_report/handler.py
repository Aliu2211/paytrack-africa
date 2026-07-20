import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
tenants_table = dynamodb.Table(os.environ["TENANTS_TABLE"])
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
analytics_table = dynamodb.Table(os.environ["ANALYTICS_TABLE"])
ses = boto3.client("ses")
cognito = boto3.client("cognito-idp")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SES_SENDER_EMAIL = os.environ["SES_SENDER_EMAIL"]
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _tenant_contacts():
    # Cognito's ListUsers Filter only supports standard attributes, not
    # custom ones -- custom:tenant_id can't be filtered server-side, so we
    # list everyone in the pool once and match tenant_id in code. Fine at
    # SME-client scale.
    contacts = {}
    pagination_token = None
    while True:
        kwargs = {"UserPoolId": COGNITO_USER_POOL_ID}
        if pagination_token:
            kwargs["PaginationToken"] = pagination_token
        result = cognito.list_users(**kwargs)
        for user in result.get("Users", []):
            attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
            tenant_id = attrs.get("custom:tenant_id")
            if tenant_id:
                contacts[tenant_id] = {
                    "email": attrs.get("email"),
                    "business_name": attrs.get("custom:business_name") or attrs.get("email"),
                }
        pagination_token = result.get("PaginationToken")
        if not pagination_token:
            break
    return contacts


def _outstanding_amount(tenant_id):
    item = analytics_table.get_item(
        Key={"tenant_id": tenant_id, "metric_key": "total_outstanding_amount"}
    ).get("Item")
    return item["metric_value"] if item else Decimal(0)


def _weekly_stats(tenant_id, week_ago, today):
    result = invoices_table.query(KeyConditionExpression=Key("tenant_id").eq(tenant_id))
    invoices = result.get("Items", [])

    sent_this_week = sum(
        1 for i in invoices if i.get("status") == "sent" and i.get("updated_at", "") >= week_ago
    )
    paid_this_week = sum(
        1 for i in invoices if i.get("status") == "paid" and i.get("updated_at", "") >= week_ago
    )
    overdue_count = sum(
        1 for i in invoices if i.get("status") == "sent" and i.get("due_date", "") < today
    )
    return sent_this_week, paid_this_week, overdue_count


def _send_report(contact, sent_this_week, paid_this_week, outstanding, overdue_count):
    body = (
        f"Weekly summary for {contact['business_name']}\n\n"
        f"Invoices sent this week: {sent_this_week}\n"
        f"Invoices paid this week: {paid_this_week}\n"
        f"Total outstanding amount: {outstanding}\n"
        f"Overdue invoices: {overdue_count}\n"
    )
    ses.send_email(
        Source=SES_SENDER_EMAIL,
        Destination={"ToAddresses": [contact["email"]]},
        Message={
            "Subject": {"Data": "PayTrack Africa: your weekly summary"},
            "Body": {"Text": {"Data": body}},
        },
    )


def lambda_handler(event, context):
    today = date.today().isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    tenant_ids = [item["tenant_id"] for item in tenants_table.scan().get("Items", [])]
    contacts = _tenant_contacts()

    tenants_processed = 0
    emails_sent = 0

    for tenant_id in tenant_ids:
        contact = contacts.get(tenant_id)
        if not contact or not contact.get("email"):
            continue

        sent_this_week, paid_this_week, overdue_count = _weekly_stats(tenant_id, week_ago, today)
        outstanding = _outstanding_amount(tenant_id)

        _send_report(contact, sent_this_week, paid_this_week, outstanding, overdue_count)
        tenants_processed += 1
        emails_sent += 1

    summary = {"tenants_processed": tenants_processed, "emails_sent": emails_sent}
    logger.info(json.dumps({"event": "invoke_end", "function": "weekly_report", **summary}, default=_decimal_default))
    return summary
