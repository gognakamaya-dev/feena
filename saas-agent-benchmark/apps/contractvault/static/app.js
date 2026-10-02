window.APP_CONFIG = {
  tabs: [{ id: "contracts", title: "Contracts", path: "/api/contracts", filter: { param: "status", options: ["draft", "in_review", "signed", "expired"] },
      columns: [["title", "Title"], ["counterparty", "Counterparty"], ["status", "Status"], ["value_cents", "Value", "money"], ["end_date", "Ends"]],
      forms: [{ id: "contract", title: "New contract", path: "/api/contracts", fields: [{ name: "title", label: "Title" }, { name: "counterparty", label: "Counterparty" }, { name: "start_date", label: "Start", type: "date" }, { name: "end_date", label: "End", type: "date" }] }] }],
  hooks: {
    validate: (form, v) => (!v.title || !v.counterparty || !v.start_date || !v.end_date ? ["All fields are required"] : []),
  },
};
