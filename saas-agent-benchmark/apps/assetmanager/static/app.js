window.APP_CONFIG = {
  tabs: [{ id: "assets", title: "Assets", path: "/api/assets", pageSize: 10, columns: [["name", "Name"], ["mime", "Type"], ["size_bytes", "Size (bytes)"]],
      actions: [{ label: "delete", method: "DELETE", path: (id) => `/api/assets/${id}` }] }],
  hooks: {
    summarize: (tab, items) => "Total: " + (items.reduce((s, a) => s + a.size_bytes, 0) / 1000000).toFixed(1) + " MB",
  },
};
