window.APP_CONFIG = {
  tabs: [{ id: "dashboards", title: "Dashboards", path: "/api/dashboards", columns: [["id", "ID"], ["name", "Name"]] },
    { id: "metrics", title: "Metrics", path: "/api/metrics/summary", columns: [["event", "Event"], ["count", "Count"]] }],
  hooks: {
    summarize: (tab, items) => (tab === "metrics" ? "Total events: " + Math.max(...items.map((r) => r.count)) : ""),
  },
};
