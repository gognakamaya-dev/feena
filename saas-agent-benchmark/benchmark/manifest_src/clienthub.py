from ._b import B
APP, PREFIX = "ClientHub", "CH"
BUGS = [
    B(1, "backend", "easy", "medium", "contact_creation", "Duplicate contact emails are accepted within an organization.", "Existing email", "POST /api/contacts with email wile@example.test", "409", "201 duplicate"),
    B(2, "frontend", "easy", "medium", "pipeline_summary", "Open pipeline total includes won and lost deals.", "Deals in closed stages", "Open Deals tab", "Only prospect/qualified/proposal summed", "All deals summed"),
    B(3, "database", "medium", "medium", "contact_search", "Search results include soft-deleted contacts.", "?q= matching a deleted contact", "GET /api/contacts?q=Gavin", "Empty", "Deleted contact returned"),
    B(4, "security", "medium", "critical", "deal_access", "Deal detail endpoint is not scoped to organization.", "Foreign deal id", "As Acme admin GET /api/deals/100", "404", "200 with Globex deal"),
    B(5, "database", "hard", "high", "contact_merge", "Merging contacts soft-deletes the duplicate but leaves its deals attached to it, so kept contact loses deals/lifetime value.", "Merge contacts that have deals", "Create contacts A,B > Create won deal on B > Merge B into A > Read A", "A lifetime value includes B's deal", "A lifetime value 0; deal orphaned", True),
    B(6, "business_logic", "hard", "high", "pipeline_report", "Moving a won deal back to an open stage keeps closed_on so it still counts as won revenue.", "Won deal reopened", "Win deal > Move to proposal > GET /api/reports/pipeline", "won_cents excludes deal", "won_cents still includes deal", True),
]
