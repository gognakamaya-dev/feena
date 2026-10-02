from ._b import B
APP, PREFIX = "AnalyticsHub", "AH"
BUGS = [
    B(1, "backend", "easy", "medium", "ingestion", "Events with blank/whitespace names are accepted.", "name '  '", "POST /api/events {name:'  '}", "400", "201"),
    B(2, "frontend", "easy", "low", "metrics_summary", "Total events summary shows the largest count instead of the sum.", "Several event types", "Open Metrics tab", "Sum of counts", "Maximum count"),
    B(3, "backend", "medium", "medium", "date_filter", "The 'to' date filter excludes events on the 'to' day itself.", "from == to date", "GET /api/metrics/count?event=signup&from=2026-03-02&to=2026-03-02", "2 events", "0 events"),
    B(4, "security", "medium", "critical", "dashboard_access", "Dashboard data endpoint is not scoped to organization.", "Foreign dashboard id", "As Acme admin GET /api/dashboards/2/data", "404", "200 Globex metrics"),
    B(5, "business_logic", "medium", "medium", "unique_users", "Anonymous events (null user_key) are counted as one unique user.", "Events without user_key", "GET /api/metrics/unique-users?event=pageview", "0", "1"),
    B(6, "business_logic", "hard", "high", "funnel", "Funnel ignores step order and counts users who completed steps in any order.", "User performs step 2 before step 1", "Ingest checkout then cart for one user > GET funnel steps=cart,checkout", "checkout step users = 0", "checkout step users = 1", True),
]
