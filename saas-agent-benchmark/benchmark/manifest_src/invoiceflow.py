from ._b import B
APP, PREFIX = "InvoiceFlow", "INV"
BUGS = [
    B(1, "business_logic", "medium", "high", "invoice_calculation", "Tax is calculated on the pre-discount subtotal instead of the discounted amount.",
      "Invoice with both discount_pct and tax_pct", "Create invoice 10x$10 with discount 20% and tax 10% > Read total", "Total 8800 cents (tax on 8000)", "Total 9000 cents (tax on 10000)"),
    B(2, "frontend", "easy", "medium", "invoice_list_pagination", "Page count uses floor, so the last partial page is unreachable.",
      "Total invoices not a multiple of page size", "Open Invoices tab with 23 invoices > Observe pager", "3 pages", "2 pages; invoices 21-23 unreachable"),
    B(3, "backend", "easy", "medium", "invoice_validation", "Invoices with no line items are accepted.",
      "POST /api/invoices with items=[] or missing", "POST invoice with empty items", "400 validation error", "201 with zero total invoice"),
    B(4, "security", "medium", "critical", "invoice_authorization", "GET /api/invoices/<id> does not scope by organization (cross-tenant read).",
      "Authenticated user of org A requests id of org B", "Login as admin@globex.test > GET /api/invoices/1", "404", "200 with Acme invoice"),
    B(5, "business_logic", "hard", "high", "refunds", "Refunding a payment leaves the invoice in 'paid' status although the balance is reopened.",
      "Refund a payment on a fully paid invoice", "Create+send invoice > Pay in full > Refund payment > Read invoice", "balance restored and status 'sent'/'partially_paid'", "balance restored but status still 'paid' (cannot be paid again)", True),
    B(6, "business_logic", "very_hard", "high", "revenue_report", "Monthly revenue report excludes payments dated on the last day of the month (exclusive end is the last day, not the first of next month).",
      "Payment with paid_on on the final day of a month", "Create+send invoice > Record payment with paid_on=2026-02-28 > GET /api/reports/revenue?month=2026-02", "Revenue includes the payment", "Revenue is 0 for that payment", True),
]
