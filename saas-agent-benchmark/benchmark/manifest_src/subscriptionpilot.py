from ._b import B
APP, PREFIX = "SubscriptionPilot", "SUB"
BUGS = [
    B(1, "backend", "easy", "medium", "subscribe", "A customer can hold duplicate active subscriptions to the same plan.", "Subscribe twice to one plan", "POST subscription customer 5 plan 1 twice", "409 on second", "201 second subscription"),
    B(2, "frontend", "easy", "medium", "mrr_summary", "MRR summary adds annual plan prices as if they were monthly.", "Annual plan among active subscriptions", "Open Subscriptions tab", "Annual price / 12", "Full annual price"),
    B(3, "business_logic", "medium", "high", "coupons", "Coupon max_redemptions is not enforced (single-use coupon works repeatedly).", "Coupon with max_redemptions 1", "Subscribe customer 4 with LAUNCH20 > Subscribe customer 5 with LAUNCH20", "409 on second use", "201 discount applied again"),
    B(4, "business_logic", "medium", "high", "trials", "Trial subscriptions are charged an initial invoice immediately.", "Plan with trial_days > 0", "POST subscription on Team plan", "trialing with no invoice", "trialing with invoice for full price"),
    B(5, "business_logic", "hard", "high", "proration", "Upgrade charges the full price difference instead of prorating for the remaining period.", "Mid-period upgrade", "Subscribe to Starter > change-plan to Pro with effective_on 2026-03-31", "proration invoice 968 (2000*15/31)", "proration invoice 2000", True),
    B(6, "business_logic", "hard", "critical", "renewal_job", "Billing run invoices a subscription scheduled to cancel at period end before cancelling it.", "cancel_at_period_end subscription reaching period end", "Subscribe > Cancel at period end > Run renew job as_of after period end > Read invoices", "No renewal invoice, status canceled", "Renewal invoice created, status canceled", True),
]
