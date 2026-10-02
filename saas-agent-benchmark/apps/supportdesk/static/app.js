window.APP_CONFIG = {
  tabs: [{ id: "tickets", title: "Tickets", path: "/api/tickets", pageSize: 10,
      columns: [["id", "#"], ["subject", "Subject"], ["status", "Status"], ["priority", "Priority"], ["requester_email", "Requester"]],
      filter: { param: "status", options: ["open", "pending", "resolved", "closed"] },
      forms: [{ id: "ticket", title: "New ticket", path: "/api/tickets", fields: [{ name: "subject", label: "Subject" }, { name: "body", label: "Details" }] }] }],
  hooks: {
    validate: (form, v) => (!v.subject || v.subject.length === 0 ? ["Subject required"] : []),
  },
};
