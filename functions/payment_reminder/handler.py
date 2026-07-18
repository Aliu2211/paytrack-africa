import json
import os
from datetime import date, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
tenants_table = dynamodb.Table(os.environ["TENANTS_TABLE"])
sns = boto3.client("sns")
ses = boto3.client("ses")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
SES_SENDER_EMAIL = os.environ["SES_SENDER_EMAIL"]


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _due_soon_invoices(tenant_id, today, horizon):
    result = invoices_table.query(
        IndexName="status-due-date-index",
        KeyConditionExpression=Key("tenant_id").eq(tenant_id) & Key("due_date").between(
            today.isoformat(), horizon.isoformat()
        ),
    )
    return result.get("Items", [])


def _remind(invoice):
    message = json.dumps(
        {
            "invoice_id": invoice["invoice_id"],
            "invoice_number": invoice["invoice_number"],
            "client_name": invoice["client_name"],
            "amount": invoice["amount"],
            "currency": invoice.get("currency", "GHS"),
            "due_date": invoice["due_date"],
        },
        default=_decimal_default,
    )

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"Payment reminder: invoice {invoice['invoice_number']}",
        Message=message,
    )

    ses.send_email(
        Source=SES_SENDER_EMAIL,
        Destination={"ToAddresses": [invoice["client_email"]]},
        Message={
            "Subject": {"Data": f"Payment reminder: invoice {invoice['invoice_number']}"},
            "Body": {
                "Text": {
                    "Data": (
                        f"Dear {invoice['client_name']},\n\n"
                        f"This is a reminder that invoice {invoice['invoice_number']} for "
                        f"{invoice.get('currency', 'GHS')} {invoice['amount']} is due on "
                        f"{invoice['due_date']}.\n\nThank you."
                    )
                }
            },
        },
    )


def lambda_handler(event, context):
    today = date.today()
    horizon = today + timedelta(days=3)

    tenant_ids = [item["tenant_id"] for item in tenants_table.scan().get("Items", [])]

    total_scanned = 0
    reminded_invoice_ids = []

    for tenant_id in tenant_ids:
        due_soon = _due_soon_invoices(tenant_id, today, horizon)
        total_scanned += len(due_soon)
        for invoice in due_soon:
            if invoice.get("status") != "sent":
                continue
            _remind(invoice)
            reminded_invoice_ids.append(invoice["invoice_id"])

    summary = {
        "total_scanned": total_scanned,
        "total_reminded": len(reminded_invoice_ids),
        "reminded_invoice_ids": reminded_invoice_ids,
    }
    print(json.dumps({"event": "payment_reminder_summary", **summary}))
    return summary
