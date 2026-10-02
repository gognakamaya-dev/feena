window.APP_CONFIG = {
  tabs: [{ id: "events", title: "Events", path: "/api/events", columns: [["title", "Title"], ["starts_on", "Date"], ["capacity", "Capacity"], ["price_cents", "Price", "money"], ["status", "Status"]],
      forms: [{ id: "event", title: "New event", path: "/api/events", fields: [{ name: "title", label: "Title" }, { name: "starts_on", label: "Date", type: "date" }, { name: "capacity", label: "Capacity", type: "number" }] }] }],
  hooks: {
    formatMoney: (c) => "$" + Math.round(c / 100),
  },
};
