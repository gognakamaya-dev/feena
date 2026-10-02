/* Shared UI runtime. Each app supplies window.APP_CONFIG in app.js (tabs, forms, hooks). */
(function () {
  const defaults = {
    pageCount: (total, size) => Math.ceil(total / size),
    summarize: () => "",
    validate: () => [],
    afterAction: () => true,
    formatMoney: (c) => "$" + (c / 100).toFixed(2),
    clientFilter: (items, text) => {
      const t = (text || "").toLowerCase();
      return t ? items.filter((r) => JSON.stringify(r).toLowerCase().includes(t)) : items;
    },
  };
  const AppUI = (window.AppUI = { token: null, hooks: null });
  AppUI.init = () => (AppUI.hooks = Object.assign({}, defaults, (window.APP_CONFIG || {}).hooks));
  AppUI.init();
  if (typeof document === "undefined") return;

  const $ = (s) => document.querySelector(s);
  const state = { tab: 0, page: 1, filter: "", search: "" };
  async function api(method, path, body) {
    const r = await fetch(path, { method, headers: { "Content-Type": "application/json",
      ...(AppUI.token ? { Authorization: "Bearer " + AppUI.token } : {}) }, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }
  const msg = (t) => { $("#msg").textContent = t || ""; };
  function login() {
    $("#main").innerHTML = '<form id="lf"><input name="email" value="admin@acme.test"><input name="password" type="password" value="demo123"><button>Sign in</button></form>';
    $("#lf").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const j = await api("POST", "/api/auth/login", { email: e.target.email.value, password: e.target.password.value });
        AppUI.token = j.token; $("#who").textContent = j.user.email; render();
      } catch (er) { msg(er.message); }
    };
  }
  async function render() {
    const cfg = APP_CONFIG, h = AppUI.hooks;
    $("#nav").innerHTML = "";
    cfg.tabs.forEach((t, i) => { const b = document.createElement("button"); b.textContent = t.title;
      b.onclick = () => { state.tab = i; state.page = 1; state.filter = ""; render(); }; $("#nav").appendChild(b); });
    const tab = cfg.tabs[state.tab], size = tab.pageSize || 10;
    $("#main").innerHTML = "Loading…";
    try {
      const q = new URLSearchParams({ page: state.page, page_size: size });
      if (state.filter && tab.filter) q.set(tab.filter.param, state.filter);
      const data = await api("GET", tab.path + "?" + q);
      const items = h.clientFilter(data.items || data, state.search);
      let html = "";
      if (tab.filter) html += '<select id="flt"><option value="">all</option>' + tab.filter.options.map((o) => `<option ${o === state.filter ? "selected" : ""}>${o}</option>`).join("") + "</select> ";
      html += '<input id="srch" placeholder="search" value="' + state.search + '">';
      html += '<div class="sum">' + h.summarize(tab.id, items, data) + "</div><table><tr>" + tab.columns.map((c) => "<th>" + c[1] + "</th>").join("") + "<th></th></tr>";
      items.forEach((r) => { html += "<tr>" + tab.columns.map((c) => "<td>" + (c[2] === "money" ? h.formatMoney(r[c[0]]) : r[c[0]] ?? "") + "</td>").join("") + "<td>" +
        (tab.actions || []).filter((a) => !a.show || a.show(r)).map((a) => `<button data-a="${a.label}" data-id="${r.id}">${a.label}</button>`).join("") + "</td></tr>"; });
      html += "</table><div class='pager'>";
      for (let p = 1; p <= h.pageCount(data.total ?? items.length, size); p++) html += `<button data-p="${p}">${p}</button>`;
      html += "</div>";
      (tab.forms || []).forEach((f, fi) => { html += `<form data-f="${fi}"><b>${f.title}</b>` + f.fields.map((x) => `<input name="${x.name}" type="${x.type || "text"}" placeholder="${x.label}">`).join("") + "<button>Save</button></form>"; });
      $("#main").innerHTML = html;
      const m = $("#main");
      if ($("#flt")) $("#flt").onchange = (e) => { state.filter = e.target.value; state.page = 1; render(); };
      $("#srch").onchange = (e) => { state.search = e.target.value; render(); };
      m.querySelectorAll("[data-p]").forEach((b) => (b.onclick = () => { state.page = +b.dataset.p; render(); }));
      m.querySelectorAll("[data-a]").forEach((b) => (b.onclick = async () => {
        const a = tab.actions.find((x) => x.label === b.dataset.a);
        try { const r = await api(a.method || "POST", a.path(b.dataset.id)); if (h.afterAction(tab.id, r)) render(); } catch (e) { msg(e.message); }
      }));
      m.querySelectorAll("form[data-f]").forEach((fm) => (fm.onsubmit = async (e) => {
        e.preventDefault();
        const f = tab.forms[+fm.dataset.f], v = {};
        f.fields.forEach((x) => { const raw = fm[x.name].value; v[x.name] = x.type === "number" ? (raw === "" ? null : +raw) : raw; });
        const errs = h.validate(f.id, v);
        if (errs.length) return msg(errs.join("; "));
        try { await api("POST", f.path, f.build ? f.build(v) : v); msg("Saved"); render(); } catch (er) { msg(er.message); }
      }));
    } catch (e) { $("#main").innerHTML = ""; msg(e.message); }
  }
  AppUI.boot = login;
})();
