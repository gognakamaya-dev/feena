window.APP_CONFIG = {
  tabs: [{ id: "jobs", title: "Jobs", path: "/api/jobs", columns: [["title", "Title"], ["department", "Department"], ["status", "Status"]],
      actions: [{ label: "close", path: (id) => `/api/jobs/${id}/close`, show: (r) => r.status === "open" }] },
    { id: "applications", title: "Candidates", path: "/api/jobs/1/applications", filter: { param: "stage", options: ["applied", "screen", "interview", "offer", "hired", "rejected"] },
      columns: [["name", "Name"], ["email", "Email"], ["stage", "Stage"]] }],
  hooks: {
    summarize: (tab, items) => (tab === "applications" ? "Active candidates: " + items.length : ""),
  },
};
