window.APP_CONFIG = {
  tabs: [{ id: "surveys", title: "Surveys", path: "/api/surveys", columns: [["title", "Title"], ["status", "Status"], ["responses", "Responses"]],
      actions: [{ label: "launch", path: (id) => `/api/surveys/${id}/launch`, show: (r) => r.status === "draft" }, { label: "close", path: (id) => `/api/surveys/${id}/close`, show: (r) => r.status === "live" }],
      forms: [{ id: "survey", title: "New survey", path: "/api/surveys", fields: [{ name: "title", label: "Title" }] }] },
    { id: "ratings", title: "Ratings", path: "/api/surveys/1/ratings", columns: [["id", "Response"], ["value", "Rating"]] }],
  hooks: {
    summarize: (tab, items, data) => (tab === "ratings" ? "Avg rating: " + Math.round(items.reduce((s, r) => s + r.value, 0) / items.length) : ""),
  },
};
