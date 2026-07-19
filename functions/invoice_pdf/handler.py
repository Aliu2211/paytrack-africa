import io
import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

dynamodb = boto3.resource("dynamodb")
invoices_table = dynamodb.Table(os.environ["INVOICES_TABLE"])
s3 = boto3.client("s3")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PDF_BUCKET_NAME = os.environ["PDF_BUCKET_NAME"]
PRESIGNED_URL_EXPIRY_SECONDS = 86400


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


def _build_pdf(invoice):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("PayTrack Africa", styles["Title"]),
        Paragraph(f"Invoice {invoice['invoice_number']}", styles["Heading2"]),
        Spacer(1, 12),
        Paragraph(f"Bill to: {invoice['client_name']} ({invoice['client_email']})", styles["Normal"]),
        Paragraph(f"Due date: {invoice['due_date']}", styles["Normal"]),
        Spacer(1, 12),
    ]

    line_items = invoice.get("line_items") or []
    table_data = [["Description", "Amount"]]
    for item in line_items:
        table_data.append([str(item.get("description", "")), str(item.get("amount", ""))])
    table_data.append(["Total", f"{invoice.get('currency', 'GHS')} {invoice['amount']}"])

    table = Table(table_data, colWidths=[350, 120])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Payment instructions: pay by the due date shown above.", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


def lambda_handler(event, context):
    tenant_id = event["requestContext"]["authorizer"]["claims"].get("custom:tenant_id")
    if not tenant_id:
        return _response(403, {"message": "No tenant assigned to this account. Contact your administrator."})
    invoice_id = event["pathParameters"]["id"]
    logger.info(json.dumps({
        "event": "invoke_start", "function": "invoice_pdf",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))

    invoice = invoices_table.get_item(Key={"tenant_id": tenant_id, "invoice_id": invoice_id}).get("Item")
    if not invoice:
        scan = invoices_table.scan(FilterExpression=Attr("invoice_id").eq(invoice_id))
        if scan.get("Items"):
            return _response(403, {"message": "Forbidden"})
        return _response(404, {"message": "Invoice not found"})

    pdf_bytes = _build_pdf(invoice)
    key = f"{tenant_id}/{invoice_id}.pdf"
    s3.put_object(Bucket=PDF_BUCKET_NAME, Key=key, Body=pdf_bytes, ContentType="application/pdf")

    pdf_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": PDF_BUCKET_NAME, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )

    logger.info(json.dumps({
        "event": "invoke_end", "function": "invoice_pdf",
        "tenant_id": tenant_id, "request_id": context.aws_request_id,
    }))
    return _response(200, {
        "invoice_id": invoice_id,
        "pdf_url": pdf_url,
        "expires_in": PRESIGNED_URL_EXPIRY_SECONDS,
    })
