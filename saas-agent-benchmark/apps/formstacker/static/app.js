window.APP_CONFIG = {
  tabs: [{ id: "forms", title: "Forms", path: "/api/forms", columns: [["title", "Title"], ["slug", "Slug"], ["status", "Status"], ["max_responses", "Limit"]],
      actions: [{ label: "publish", path: (id) => `/api/forms/${id}/publish`, show: (r) => r.status === "draft" }],
      forms: [{ id: "form", title: "New form", path: "/api/forms", fields: [{ name: "title", label: "Title" }, { name: "slug", label: "Slug" }, { name: "max_responses", label: "Max responses", type: "number" }] }] }],
  hooks: {
    validate: (form, v) => {
      const errs = [];
      if (form === "form" && !v.title) errs.push("Title required");
      if (form === "submit" && !(v.email || "").includes("@")) errs.push("Valid email required");
      return errs;
    },
  },
};
