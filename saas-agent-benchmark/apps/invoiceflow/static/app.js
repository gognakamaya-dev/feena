window.APP_CONFIG = {
  tabs: [
    { id: "invoices", title: "Invoices", path: "/api/invoices", pageSize: 10,
      columns: [["number", "Number"], ["customer_name", "Customer"], ["status", "Status"], ["total_cents", "Total", "money"], ["balance_cents", "Balance", "money"]],
      filter: { param: "status", options: ["draft", "sent", "partially_paid", "paid", "void"] },
      actions: [{ label: "send", path: (id) => `/api/invoices/${id}/send`, show: (r) => r.status === "draft" },
                { label: "void", path: (id) => `/api/invoices/${id}/void`, show: (r) => r.status !== "paid" && r.status !== "void" }] },
    { id: "customers", title: "Customers", path: "/api/customers", columns: [["name", "Name"], ["email", "Email"]] },
  ],
  hooks: {
    pageCount: (total, size) => Math.floor(total / size),
    summarize: (tab, items) => tab === "invoices" ? "Outstanding: $" + (items.reduce((s, r) => s + r.balance_cents, 0) / 100).toFixed(2) : "",
  },
};
