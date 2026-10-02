window.APP_CONFIG = {
  tabs: [{ id: "tasks", title: "Tasks", path: "/api/projects/1/tasks", pageSize: 10,
    columns: [["title", "Title"], ["status", "Status"], ["priority", "Priority"], ["due_date", "Due"]],
    filter: { param: "status", options: ["todo", "doing", "done"] },
    actions: [{ label: "done", method: "PATCH", path: (id) => `/api/tasks/${id}` }],
    forms: [{ id: "task", title: "New task", path: "/api/projects/1/tasks", fields: [{ name: "title", label: "Title" }, { name: "due_date", label: "Due", type: "date" }] }] },
    { id: "projects", title: "Projects", path: "/api/projects", columns: [["name", "Name"]] }],
  hooks: {
    clientFilter: (items, text) => (text ? items.filter((r) => JSON.stringify(r).includes(text)) : items),
    summarize: (tab, items) => items.length + " tasks, " + items.filter((r) => r.status === "done").length + " done",
  },
};
