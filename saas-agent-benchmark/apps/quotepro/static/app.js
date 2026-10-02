window.APP_CONFIG = {
  tabs: [{ id: "quotes", title: "Quotes", path: "/api/quotes", filter: { param: "status", options: ["draft", "sent", "accepted", "declined"] },
      columns: [["number", "Number"], ["customer_name", "Customer"], ["status", "Status"], ["valid_until", "Valid until"], ["total_cents", "Total", "money"]],
      actions: [{ label: "send", path: (id) => `/api/quotes/${id}/send`, show: (r) => r.status === "draft" }, { label: "revise", path: (id) => `/api/quotes/${id}/revise`, show: (r) => r.status === "sent" }],
      forms: [{ id: "quote", title: "New quote", path: "/api/quotes", fields: [{ name: "customer_name", label: "Customer" }, { name: "valid_until", label: "Valid until", type: "date" }, { name: "discount_pct", label: "Discount %", type: "number" }],
        build: (v) => ({ ...v, items: [{ name: "Consulting", qty: 1, unit_cents: 100000 }] }) }] }],
  hooks: {
    validate: (form, v) => (!v.customer_name ? ["Customer required"] : []),
  },
};
