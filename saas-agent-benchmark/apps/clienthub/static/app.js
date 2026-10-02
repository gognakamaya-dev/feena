window.APP_CONFIG = {
  tabs: [{ id: "contacts", title: "Contacts", path: "/api/contacts", columns: [["name", "Name"], ["email", "Email"], ["lifecycle", "Lifecycle"]],
      forms: [{ id: "contact", title: "New contact", path: "/api/contacts", fields: [{ name: "name", label: "Name" }, { name: "email", label: "Email" }] }] },
    { id: "deals", title: "Deals", path: "/api/deals", filter: { param: "stage", options: ["prospect", "qualified", "proposal", "won", "lost"] },
      columns: [["title", "Title"], ["contact_name", "Contact"], ["stage", "Stage"], ["amount_cents", "Amount", "money"]] }],
  hooks: {
    summarize: (tab, items) => tab === "deals" ? "Open pipeline: $" + (items.reduce((s, d) => s + d.amount_cents, 0) / 100).toFixed(2) : "",
  },
};
