window.APP_CONFIG = {
  tabs: [{ id: "appointments", title: "Appointments", path: "/api/appointments", pageSize: 10,
      columns: [["start", "Start"], ["customer_name", "Customer"], ["staff_id", "Staff"], ["status", "Status"], ["price_cents", "Price", "money"]],
      filter: { param: "status", options: ["booked", "cancelled", "completed"] },
      actions: [{ label: "cancel", path: (id) => `/api/appointments/${id}/cancel`, show: (r) => r.status === "booked" }] },
    { id: "services", title: "Services", path: "/api/services", columns: [["name", "Name"], ["duration_min", "Minutes"], ["price_cents", "Price", "money"]] }],
  hooks: {
    summarize: (tab, items) => tab === "appointments" ? "Revenue: $" + (items.reduce((s, r) => s + r.price_cents, 0) / 100).toFixed(2) : "",
  },
};
