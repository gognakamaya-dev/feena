window.APP_CONFIG = {
  tabs: [{ id: "products", title: "Products", path: "/api/products", pageSize: 10,
      columns: [["sku", "SKU"], ["name", "Name"], ["on_hand", "On hand"], ["reserved", "Reserved"], ["available", "Available"], ["reorder_level", "Reorder at"]],
      forms: [{ id: "product", title: "New product", path: "/api/products", fields: [{ name: "sku", label: "SKU" }, { name: "name", label: "Name" }, { name: "on_hand", label: "Qty", type: "number" }] }] }],
  hooks: {
    summarize: (tab, items) => "Low stock: " + items.filter((p) => p.on_hand < p.reorder_level).length,
  },
};
