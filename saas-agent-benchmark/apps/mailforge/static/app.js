window.APP_CONFIG = {
  tabs: [{ id: "campaigns", title: "Campaigns", path: "/api/campaigns", columns: [["subject", "Subject"], ["status", "Status"], ["recipient_count", "Recipients"], ["scheduled_at", "Scheduled"]],
      actions: [{ label: "send", path: (id) => `/api/campaigns/${id}/send`, show: (r) => r.status !== "sent" }] },
    { id: "lists", title: "Lists", path: "/api/lists", columns: [["name", "Name"], ["members", "Members"]] }],
  hooks: {
    summarize: (tab, items) => tab === "campaigns" ? "Total recipients: " + items.length : "",
  },
};
