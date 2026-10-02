window.APP_CONFIG = {
  tabs: [{ id: "expenses", title: "Expenses", path: "/api/expenses", pageSize: 10,
      columns: [["incurred_on", "Date"], ["category", "Category"], ["description", "Description"], ["amount_cents", "Amount", "money"], ["status", "Status"]],
      filter: { param: "status", options: ["draft", "submitted", "approved", "rejected", "reimbursed"] },
      actions: [{ label: "submit", path: (id) => `/api/expenses/${id}/submit`, show: (r) => r.status === "draft" },
                { label: "approve", path: (id) => `/api/expenses/${id}/approve`, show: (r) => r.status === "submitted" }],
      forms: [{ id: "expense", title: "New expense", path: "/api/expenses", fields: [{ name: "category", label: "Category" }, { name: "amount_cents", label: "Amount (cents)", type: "number" }, { name: "incurred_on", label: "Date", type: "date" }] }] }],
  hooks: {
    validate: (form, v) => (v.amount_cents < 0 ? ["Amount must be positive"] : []),
  },
};
