window.APP_CONFIG = {
  tabs: [{ id: "subscriptions", title: "Subscriptions", path: "/api/subscriptions", filter: { param: "status", options: ["trialing", "active", "past_due", "canceled"] },
      columns: [["id", "ID"], ["customer_id", "Customer"], ["plan_id", "Plan"], ["status", "Status"], ["period_end", "Renews"]],
      actions: [{ label: "cancel", path: (id) => `/api/subscriptions/${id}/cancel`, show: (r) => r.status !== "canceled" }] },
    { id: "plans", title: "Plans", path: "/api/plans", columns: [["name", "Name"], ["price_cents", "Price", "money"], ["interval", "Interval"]] }],
  hooks: {
    summarize: (tab, items) => (tab === "subscriptions" ? "MRR: $" + (items.filter((s) => s.status === "active").reduce((t, s) => t + s.price_cents, 0) / 100).toFixed(2) : ""),
  },
};
