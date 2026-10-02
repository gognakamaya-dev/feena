from ._b import B
APP, PREFIX = "StockPilot", "SP"
BUGS = [
    B(1, "backend", "easy", "medium", "product_creation", "Duplicate SKUs are accepted within an organization.", "Create product with existing SKU", "POST /api/products with sku WID-001", "409", "201 duplicate SKU"),
    B(2, "frontend", "easy", "low", "low_stock_summary", "Low-stock count uses < rather than <= reorder level.", "on_hand equals reorder_level", "View products with on_hand == reorder_level", "Counted as low stock", "Not counted"),
    B(3, "business_logic", "medium", "medium", "low_stock_report", "Low-stock report ignores reserved quantity.", "Confirmed order reserving stock", "Confirm order reserving 35 of 40 > GET low-stock report", "Product listed (available 5 <= 10)", "Product missing", True),
    B(4, "security", "medium", "high", "adjust_authorization", "Viewer role can adjust stock.", "viewer login", "POST /api/products/1/adjust as viewer", "403", "200"),
    B(5, "business_logic", "hard", "high", "order_cancellation", "Cancelling a confirmed order does not release reserved stock.", "Confirm then cancel", "Confirm order > Cancel > Read available", "available restored", "available permanently reduced", True),
    B(6, "business_logic", "hard", "critical", "stock_adjustment", "Manual adjustment may reduce on-hand below reserved quantity, later driving stock negative on shipment.", "Reservation exists, then large negative adjustment", "Confirm order for 30 > Adjust -35 > Ship order > Read on_hand", "409 on adjust", "adjust succeeds; shipping makes on_hand negative", True),
]
