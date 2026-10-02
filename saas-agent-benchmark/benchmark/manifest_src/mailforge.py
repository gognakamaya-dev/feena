from ._b import B
APP, PREFIX = "MailForge", "MF"
BUGS = [
    B(1, "backend", "easy", "low", "subscriber_validation", "Subscriber email format is not validated.", "Malformed email", "POST /api/lists/1/subscribers {email:'not-an-email'}", "400", "201 stored"),
    B(2, "frontend", "easy", "low", "campaign_summary", "Total recipients summary counts campaigns instead of summing recipients.", "Campaign list with recipient counts", "Open Campaigns tab", "Sum of recipient_count", "Number of rows"),
    B(3, "business_logic", "medium", "critical", "campaign_delivery", "Campaigns are sent to unsubscribed contacts (only bounced are excluded).", "List with an unsubscribed contact", "Create campaign for list 1 > Send > Read recipient_count", "6 recipients", "7 recipients including unsubscribed"),
    B(4, "security", "medium", "high", "campaign_stats_access", "Campaign stats endpoint is not scoped to organization.", "Campaign id from another org", "As Acme admin GET /api/campaigns/3/stats", "404", "200 with other org stats"),
    B(5, "business_logic", "hard", "critical", "resubscribe", "Adding an address that previously unsubscribed silently re-subscribes it.", "Unsubscribed address re-added", "Add subscriber > Unsubscribe > Add same email again > Read status", "Status remains unsubscribed", "Status flips to subscribed", True),
    B(6, "backend", "very_hard", "medium", "scheduler", "Scheduler compares scheduled_at to now as strings, ignoring UTC offsets.", "scheduled_at with non-UTC offset that is already past in UTC", "Create campaign > Schedule 2026-03-15T11:00:00+02:00 > Run scheduler", "Campaign sent (09:00Z is past)", "Campaign not sent", True),
]
