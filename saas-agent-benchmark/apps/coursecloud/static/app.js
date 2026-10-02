window.APP_CONFIG = {
  tabs: [{ id: "courses", title: "Courses", path: "/api/courses", columns: [["title", "Title"], ["status", "Status"], ["price_cents", "Price", "money"]],
      actions: [{ label: "enroll", path: (id) => `/api/courses/${id}/enroll`, show: (r) => r.status === "published" }] }],
  hooks: {
    summarize: (tab, items) => "Published courses: " + items.length,
  },
};
