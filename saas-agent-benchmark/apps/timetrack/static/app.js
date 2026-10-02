window.APP_CONFIG = {
  tabs: [{ id: "entries", title: "Time entries", path: "/api/entries", pageSize: 10, columns: [["project", "Project"], ["start_at", "Start"], ["end_at", "End"], ["minutes", "Minutes"]],
      forms: [{ id: "entry", title: "Add entry", path: "/api/entries", fields: [{ name: "project", label: "Project" }, { name: "start_at", label: "Start (YYYY-MM-DDTHH:MM)" }, { name: "end_at", label: "End" }] }] }],
  hooks: {
    summarize: (tab, items) => "Total hours: " + Math.round(items.reduce((s, e) => s + (e.minutes || 0), 0) / 60),
  },
};
