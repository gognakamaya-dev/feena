window.APP_CONFIG = {
  tabs: [{ id: "employees", title: "Employees", path: "/api/employees", pageSize: 10,
      columns: [["name", "Name"], ["email", "Email"], ["title", "Title"], ["status", "Status"]] },
    { id: "teams", title: "Teams", path: "/api/teams", columns: [["name", "Team"], ["headcount", "Headcount"]] }],
  hooks: {
    summarize: (tab, items) => tab === "employees" ? "Headcount: " + items.length : "",
  },
};
