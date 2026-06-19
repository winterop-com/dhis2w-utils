/*
 * DHIS2 Sharing Explorer runtime.
 *
 * Reads window.__SHARING__ (the serialized SharingGraph + run meta) and renders the interactive,
 * offline explorer: object tree, exposure triage, by-principal and by-role pivots, and a detail
 * panel that answers "who can concretely read or write this object, and by what path" from the
 * server-computed effective-access closure. Vanilla DOM (names rendered via textContent, never
 * innerHTML) plus d3 for the severity-distribution bar. No network, no framework.
 */
(function () {
  "use strict";

  var ROOT = document.getElementById("app");
  var DATA = window.__SHARING__;
  if (!DATA || !DATA.graph) {
    ROOT.appendChild(h("div", { class: "empty" }, "No sharing data found (window.__SHARING__ is missing)."));
    return;
  }
  var G = DATA.graph;
  var META = DATA.meta || {};

  // ---- tiny hyperscript helper -------------------------------------------------
  function h(tag, props) {
    var e = document.createElement(tag);
    if (props) {
      for (var k in props) {
        var v = props[k];
        if (v == null) continue;
        if (k === "class") e.className = v;
        else if (k === "text") e.textContent = v;
        else if (k === "style") e.setAttribute("style", v);
        else if (k.slice(0, 2) === "on" && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
        else e.setAttribute(k, v);
      }
    }
    for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
    return e;
  }
  function append(e, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { append(e, x); }); return; }
    e.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); }

  // ---- indexes -----------------------------------------------------------------
  var objByUid = {}, userByUid = {}, groupByUid = {}, roleByUid = {}, effByObj = {};
  G.objects.forEach(function (o) { objByUid[o.uid] = o; });
  G.users.forEach(function (u) { userByUid[u.uid] = u; });
  G.groups.forEach(function (g) { groupByUid[g.uid] = g; });
  G.roles.forEach(function (r) { roleByUid[r.uid] = r; });
  (G.effective || []).forEach(function (e) { effByObj[e.object_uid] = e; });

  var sharesByObj = {}, sharesToPrincipal = {};
  G.shares.forEach(function (s) {
    (sharesByObj[s.object_uid] = sharesByObj[s.object_uid] || []).push(s);
    (sharesToPrincipal[s.principal_uid] = sharesToPrincipal[s.principal_uid] || []).push(s);
  });
  var membersByGroup = {}, groupsByUser = {};
  G.memberships.forEach(function (m) {
    (membersByGroup[m.group_uid] = membersByGroup[m.group_uid] || []).push(m.user_uid);
    (groupsByUser[m.user_uid] = groupsByUser[m.user_uid] || []).push(m.group_uid);
  });
  var rolesByUser = {}, usersByRole = {};
  G.role_grants.forEach(function (r) {
    (rolesByUser[r.user_uid] = rolesByUser[r.user_uid] || []).push(r.role_uid);
    (usersByRole[r.role_uid] = usersByRole[r.role_uid] || []).push(r.user_uid);
  });
  var objsByType = {};
  G.objects.forEach(function (o) { (objsByType[o.type] = objsByType[o.type] || []).push(o); });

  // ---- exposure classification (mirrors the sharing check) ---------------------
  var SEV = { crit: 0, high: 1, med: 2, low: 3, none: 4 };
  function exposure(o) {
    var p = o.public || {}, db = o.data_bearing;
    if (o.external) return { sev: "high", label: "Externally accessible" };
    if (db && (p.meta_write || p.data_write)) return { sev: "high", label: "Public write (data-bearing)" };
    if (!db && p.meta_write) return { sev: "med", label: "Public write (metadata)" };
    if (o.type === "sqlView" && p.meta_read) return { sev: "med", label: "SQL view readable by all" };
    if (db && p.data_read) return { sev: "med", label: "Public data read" };
    return { sev: "none", label: "Restricted sharing" };
  }
  function worstSev(list) {
    var w = "none";
    list.forEach(function (o) { if (SEV[exposure(o).sev] < SEV[w]) w = exposure(o).sev; });
    return w;
  }

  // ---- access rendering --------------------------------------------------------
  function bit(on, ch) { return h("span", { class: on ? "on" : "off" }, ch); }
  function accessChip(a) {
    a = a || {};
    return h("span", { class: "access" },
      "M:", bit(a.meta_read, "r"), bit(a.meta_write, "w"),
      " D:", bit(a.data_read, "r"), bit(a.data_write, "w"));
  }

  function name(node, fallback) {
    if (!node) return fallback || "(unknown)";
    return node.name || node.username || node.display_name || node.uid || fallback || "(unknown)";
  }
  function principalName(uid) {
    return userByUid[uid] ? name(userByUid[uid]) : groupByUid[uid] ? name(groupByUid[uid]) : uid;
  }

  // ---- state + routing ---------------------------------------------------------
  var state = { mode: "tree", selected: null, query: "", open: {}, theme: initialTheme() };
  var MODES = [
    { key: "tree", label: "Object tree" },
    { key: "triage", label: "Exposure triage" },
    { key: "principals", label: "By principal" },
    { key: "roles", label: "By role" },
  ];

  function initialTheme() {
    try {
      var saved = localStorage.getItem("dhis2_sharing_theme");
      if (saved) return saved;
    } catch (e) {}
    return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }
  function setTheme(t) {
    state.theme = t;
    try { localStorage.setItem("dhis2_sharing_theme", t); } catch (e) {}
    document.documentElement.setAttribute("data-theme", t);
    render();
  }

  var suppressHash = false;
  function select(kind, uid) {
    state.selected = { kind: kind, uid: uid };
    suppressHash = true;
    location.hash = "#" + kind + "/" + uid;
    suppressHash = false;
    render();
  }
  function applyHash() {
    var m = /^#([a-z]+)\/(.+)$/.exec(location.hash || "");
    if (!m) return;
    if (m[1] === "mode") { state.mode = m[2]; state.selected = null; }
    else { state.selected = { kind: m[1], uid: decodeURIComponent(m[2]) }; }
  }
  window.addEventListener("hashchange", function () { if (!suppressHash) { applyHash(); render(); } });

  // ---- render ------------------------------------------------------------------
  function render() {
    document.documentElement.setAttribute("data-theme", state.theme);
    clear(ROOT);
    ROOT.appendChild(renderHeader());
    var layout = h("div", { class: "layout" });
    var main = h("div", {});
    if (G.truncated) {
      main.appendChild(h("div", { class: "banner" },
        "Showing a capped slice of the access graph. " + (G.truncation_note || "")));
    }
    main.appendChild(renderToolbar());
    main.appendChild(renderMode());
    main.appendChild(renderCaveats());
    layout.appendChild(main);
    layout.appendChild(h("div", { class: "detail-wrap" }, renderDetail()));
    ROOT.appendChild(layout);
  }

  function renderHeader() {
    var counts = G.objects.length + " objects · " + G.users.length + " users · " +
      G.groups.length + " groups · " + G.roles.length + " roles";
    return h("header", { class: "top" },
      h("div", { class: "top-inner" },
        h("div", {},
          h("div", { class: "wordmark" }, "DHIS2 ", h("em", {}, "Sharing Explorer")),
          h("div", { class: "kicker" }, "Effective-access reasoning · read-only")),
        h("div", { class: "grow" }),
        h("div", { class: "meta-strip" },
          kv("Target", (META.target || G.target || "").replace(/^https?:\/\//, "")),
          kv("Version", META.version || "-"),
          kv("Generated", (META.generated || G.generated_at || "").slice(0, 16).replace("T", " ")),
          kv("Graph", counts)),
        themeToggle()));
  }
  function kv(k, v) { return h("span", {}, k + " ", h("b", {}, v)); }
  function themeToggle() {
    return h("div", { class: "theme-toggle", role: "group", "aria-label": "Theme" },
      h("button", { class: state.theme === "light" ? "active" : "", title: "Light", onclick: function () { setTheme("light"); } }, "☀"),
      h("button", { class: state.theme === "dark" ? "active" : "", title: "Dark", onclick: function () { setTheme("dark"); } }, "☾"));
  }

  function renderToolbar() {
    var tabs = h("div", { class: "tabs" }, MODES.map(function (m) {
      return h("button", {
        class: state.mode === m.key ? "active" : "",
        onclick: function () { state.mode = m.key; suppressHash = true; location.hash = "#mode/" + m.key; suppressHash = false; render(); },
      }, m.label);
    }));
    var search = h("div", { class: "search" },
      h("input", {
        type: "search", placeholder: "Search by name…", value: state.query,
        oninput: function (e) { state.query = e.target.value; renderInto(); },
      }));
    return h("div", { class: "toolbar" }, tabs, search);
  }

  // Re-render only the mode panel + detail (keeps the search box focused while typing).
  function renderInto() {
    var main = ROOT.querySelector(".layout > div");
    var panel = main.querySelector(".mode-panel");
    if (panel) { var fresh = renderMode(); panel.replaceWith(fresh); }
    var dw = ROOT.querySelector(".detail-wrap");
    if (dw) { clear(dw); dw.appendChild(renderDetail()); }
  }

  function matches(text) {
    return !state.query || String(text || "").toLowerCase().indexOf(state.query.toLowerCase()) >= 0;
  }

  function renderMode() {
    if (state.mode === "tree") return renderTree();
    if (state.mode === "triage") return renderTriage();
    if (state.mode === "principals") return renderPrincipals();
    return renderRoles();
  }

  // ---- mode: object tree -------------------------------------------------------
  function renderTree() {
    var panel = h("div", { class: "panel mode-panel" });
    panel.appendChild(h("div", { class: "panel-head" },
      h("div", { class: "panel-title" }, "Objects by type"),
      h("div", { class: "panel-sub" }, "Exposed objects first; click an object for its effective access")));
    panel.appendChild(severityChart());
    var list = h("div", { class: "scroll" });
    var types = Object.keys(objsByType).sort(function (a, b) {
      return SEV[worstSev(objsByType[a])] - SEV[worstSev(objsByType[b])] || a.localeCompare(b);
    });
    types.forEach(function (t) {
      var objs = objsByType[t].slice().sort(function (a, b) {
        return SEV[exposure(a).sev] - SEV[exposure(b).sev] || name(a).localeCompare(name(b));
      }).filter(function (o) { return matches(o.name); });
      if (!objs.length) return;
      var openKey = "type:" + t;
      var isOpen = state.open[openKey] || !!state.query;
      var exposed = objsByType[t].filter(function (o) { return exposure(o).sev !== "none"; }).length;
      list.appendChild(h("div", {
        class: "row", onclick: function () { state.open[openKey] = !isOpen; renderInto(); },
      },
        h("span", { class: "twisty " + (isOpen ? "open" : "") }, "›"),
        h("span", { class: "sev-dot sev-" + worstSev(objsByType[t]) }),
        h("span", { class: "name", style: "font-weight:600;" }, t),
        h("span", { class: "meta" }, exposed + " exposed"),
        h("span", { class: "count-pill" }, String(objsByType[t].length))));
      if (isOpen) {
        objs.forEach(function (o) { list.appendChild(objectRow(o, 1)); });
      }
    });
    if (!list.firstChild) list.appendChild(h("div", { class: "empty" }, "No objects match “" + state.query + "”."));
    panel.appendChild(list);
    return panel;
  }

  function objectRow(o, depth) {
    var ex = exposure(o);
    var sel = state.selected && state.selected.kind === "object" && state.selected.uid === o.uid;
    var badges = [];
    if (o.external) badges.push(h("span", { class: "badge ext" }, "EXT"));
    if (o.data_bearing) badges.push(h("span", { class: "badge" }, "DATA"));
    return h("div", { class: "row" + (sel ? " sel" : ""), onclick: function () { select("object", o.uid); } },
      h("span", { class: "indent", style: "width:" + (depth * 16) + "px;" }),
      h("span", { class: "sev-dot sev-" + ex.sev, title: ex.label }),
      h("span", { class: "name" }, name(o)),
      badges,
      accessChip(o.public));
  }

  // ---- mode: exposure triage ---------------------------------------------------
  function renderTriage() {
    var panel = h("div", { class: "panel mode-panel" });
    panel.appendChild(h("div", { class: "panel-head" },
      h("div", { class: "panel-title" }, "Exposure triage"),
      h("div", { class: "panel-sub" }, "Publicly or externally reachable objects, worst first")));
    var list = h("div", { class: "scroll" });
    var exposed = G.objects.filter(function (o) { return exposure(o).sev !== "none" && matches(o.name); })
      .sort(function (a, b) { return SEV[exposure(a).sev] - SEV[exposure(b).sev] || name(a).localeCompare(name(b)); });
    exposed.forEach(function (o) {
      var ex = exposure(o);
      var sel = state.selected && state.selected.kind === "object" && state.selected.uid === o.uid;
      list.appendChild(h("div", { class: "row" + (sel ? " sel" : ""), onclick: function () { select("object", o.uid); } },
        h("span", { class: "sev-dot sev-" + ex.sev }),
        h("span", { class: "badge" }, o.type),
        h("span", { class: "name" }, name(o)),
        h("span", { class: "meta" }, ex.label),
        accessChip(o.public)));
    });
    if (!list.firstChild) list.appendChild(h("div", { class: "empty" }, "No exposed objects in this slice."));
    panel.appendChild(list);
    return panel;
  }

  // ---- mode: by principal ------------------------------------------------------
  function renderPrincipals() {
    var panel = h("div", { class: "panel mode-panel" });
    panel.appendChild(h("div", { class: "panel-head" },
      h("div", { class: "panel-title" }, "Principals"),
      h("div", { class: "panel-sub" }, "Users and groups; click to see what they can reach")));
    var list = h("div", { class: "scroll" });
    var groups = G.groups.filter(function (g) { return matches(g.name); })
      .sort(function (a, b) { return name(a).localeCompare(name(b)); });
    var users = G.users.filter(function (u) { return matches(u.username) || matches(u.display_name); })
      .sort(function (a, b) { return name(a).localeCompare(name(b)); });
    if (groups.length) list.appendChild(subhead("Groups (" + groups.length + ")"));
    groups.forEach(function (g) {
      var sel = state.selected && state.selected.kind === "group" && state.selected.uid === g.uid;
      list.appendChild(h("div", { class: "row" + (sel ? " sel" : ""), onclick: function () { select("group", g.uid); } },
        h("span", { class: "badge" }, "GROUP"),
        h("span", { class: "name" }, name(g)),
        h("span", { class: "count-pill" }, (g.member_count || 0) + " members")));
    });
    if (users.length) list.appendChild(subhead("Users (" + users.length + ")"));
    users.forEach(function (u) {
      var sel = state.selected && state.selected.kind === "user" && state.selected.uid === u.uid;
      list.appendChild(h("div", { class: "row" + (sel ? " sel" : ""), onclick: function () { select("user", u.uid); } },
        h("span", { class: "badge" + (u.superuser ? " su" : "") }, u.superuser ? "SUPER" : "USER"),
        h("span", { class: "name" }, name(u)),
        u.disabled ? h("span", { class: "meta" }, "disabled") : null));
    });
    if (!list.firstChild) list.appendChild(h("div", { class: "empty" }, "No principals match."));
    panel.appendChild(list);
    return panel;
  }
  function subhead(t) {
    return h("div", { class: "row", style: "cursor:default;font-family:'Space Mono',monospace;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:var(--faint2);" }, t);
  }

  // ---- mode: by role -----------------------------------------------------------
  function renderRoles() {
    var panel = h("div", { class: "panel mode-panel" });
    panel.appendChild(h("div", { class: "panel-head" },
      h("div", { class: "panel-title" }, "Roles"),
      h("div", { class: "panel-sub" }, "Authority reach; ALL-granting roles confer superuser")));
    var list = h("div", { class: "scroll" });
    var roles = G.roles.filter(function (r) { return matches(r.name); }).sort(function (a, b) {
      return (b.grants_all - a.grants_all) || name(a).localeCompare(name(b));
    });
    roles.forEach(function (r) {
      var sel = state.selected && state.selected.kind === "role" && state.selected.uid === r.uid;
      list.appendChild(h("div", { class: "row" + (sel ? " sel" : ""), onclick: function () { select("role", r.uid); } },
        h("span", { class: "badge" + (r.grants_all ? " su" : "") }, r.grants_all ? "ALL" : "ROLE"),
        h("span", { class: "name" }, name(r)),
        h("span", { class: "meta" }, (r.authorities ? r.authorities.length : 0) + " auth"),
        h("span", { class: "count-pill" }, (r.member_count || 0) + " members")));
    });
    if (!list.firstChild) list.appendChild(h("div", { class: "empty" }, "No roles match."));
    panel.appendChild(list);
    return panel;
  }

  // ---- detail panel ------------------------------------------------------------
  function renderDetail() {
    var box = h("div", { class: "detail" });
    var s = state.selected;
    if (!s) {
      box.appendChild(h("div", { class: "empty" }, "Select an object or principal to inspect its access."));
      return box;
    }
    if (s.kind === "object") return objectDetail(box, objByUid[s.uid]);
    if (s.kind === "user") return userDetail(box, userByUid[s.uid]);
    if (s.kind === "group") return groupDetail(box, groupByUid[s.uid]);
    if (s.kind === "role") return roleDetail(box, roleByUid[s.uid]);
    box.appendChild(h("div", { class: "empty" }, "Unknown selection."));
    return box;
  }

  function head(box, type, title) {
    box.appendChild(h("div", { class: "dhead" },
      h("div", { class: "dtype" }, type), h("div", { class: "dname" }, title)));
  }
  function label(t) { return h("div", { class: "section-label" }, t); }
  function kvRow(k, v) { return h("div", { class: "kv" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v)); }
  function link(kind, uid, text) {
    return h("a", { href: "#" + kind + "/" + uid, onclick: function (e) { e.preventDefault(); select(kind, uid); } }, text);
  }

  function objectDetail(box, o) {
    if (!o) { box.appendChild(h("div", { class: "empty" }, "Object not in graph.")); return box; }
    var ex = exposure(o);
    head(box, o.type + (o.data_bearing ? " · data-bearing" : ""), name(o));
    var body = h("div", { class: "dbody" });
    body.appendChild(h("div", { class: "kv" }, h("span", { class: "k" }, "Exposure"),
      h("span", { class: "v" }, h("span", { class: "sev-dot sev-" + ex.sev, style: "display:inline-block;margin-right:6px;" }), ex.label)));
    body.appendChild(kvRow("UID", o.uid));
    if (o.code) body.appendChild(kvRow("Code", o.code));
    body.appendChild(h("div", { class: "kv" }, h("span", { class: "k" }, "Public access"), h("span", { class: "v" }, accessChip(o.public))));
    body.appendChild(kvRow("External", o.external ? "yes — anonymous" : "no"));
    if (o.owner) body.appendChild(h("div", { class: "kv" }, h("span", { class: "k" }, "Owner"),
      h("span", { class: "v" }, userByUid[o.owner] ? link("user", o.owner, name(userByUid[o.owner])) : o.owner)));

    var eff = effByObj[o.uid];
    if (eff) {
      body.appendChild(label("Effective access (sharing level)"));
      body.appendChild(h("div", { class: "counts" },
        countBox("Meta read", eff.meta_readers, eff.public_meta_read),
        countBox("Meta write", eff.meta_writers, eff.public_meta_write),
        countBox("Data read", eff.data_readers, eff.public_data_read),
        countBox("Data write", eff.data_writers, eff.public_data_write)));
      body.appendChild(label("How — grant paths"));
      (eff.grants || []).forEach(function (gr) { body.appendChild(grantRow(gr)); });
    }

    var shares = sharesByObj[o.uid] || [];
    if (shares.length) {
      body.appendChild(label("Explicit shares (" + shares.length + ")"));
      shares.forEach(function (sh) {
        var isGroup = sh.principal_kind === "group";
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" }, isGroup ? "group" : "user"),
          h("span", { class: "gname" }, link(isGroup ? "group" : "user", sh.principal_uid, principalName(sh.principal_uid))),
          accessChip(sh.access)));
      });
    }
    box.appendChild(body);
    return box;
  }
  function countBox(lbl, count, isPublic) {
    return h("div", { class: "countbox" },
      h("div", { class: "cl" }, lbl),
      h("div", { class: "cv" }, isPublic ? [String(count), h("small", {}, " all users")] : String(count)));
  }
  function grantRow(gr) {
    var who = gr.kind === "public" ? "every authenticated user"
      : gr.kind === "external" ? "anyone (no login)"
        : gr.kind === "superuser" ? "all superusers"
          : principalName(gr.principal_uid);
    var linkable = (gr.kind === "owner" || gr.kind === "direct") ? "user" : gr.kind === "group" ? "group" : null;
    return h("div", { class: "grant" },
      h("span", { class: "gkind" }, gr.kind),
      h("span", { class: "gname" }, linkable && gr.principal_uid ? link(linkable, gr.principal_uid, who) : who),
      accessChip(gr.access),
      h("span", { class: "gcount" }, "×" + (gr.subject_count || 0)));
  }

  function userDetail(box, u) {
    if (!u) { box.appendChild(h("div", { class: "empty" }, "User not in graph.")); return box; }
    head(box, "User" + (u.superuser ? " · superuser" : ""), name(u));
    var body = h("div", { class: "dbody" });
    body.appendChild(kvRow("UID", u.uid));
    if (u.display_name) body.appendChild(kvRow("Display name", u.display_name));
    body.appendChild(kvRow("Disabled", u.disabled ? "yes" : "no"));
    body.appendChild(kvRow("Superuser (ALL)", u.superuser ? "yes — bypasses sharing" : "no"));
    if (u.last_login) body.appendChild(kvRow("Last login", String(u.last_login).slice(0, 10)));

    var roles = rolesByUser[u.uid] || [];
    if (roles.length) {
      body.appendChild(label("Roles (" + roles.length + ")"));
      roles.forEach(function (rid) {
        var r = roleByUid[rid];
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" + (r && r.grants_all ? " " : "") }, r && r.grants_all ? "ALL" : "role"),
          h("span", { class: "gname" }, link("role", rid, r ? name(r) : rid))));
      });
    }
    var groups = groupsByUser[u.uid] || [];
    if (groups.length) {
      body.appendChild(label("Groups (" + groups.length + ")"));
      groups.forEach(function (gid) {
        var g = groupByUid[gid];
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" }, "group"),
          h("span", { class: "gname" }, link("group", gid, g ? name(g) : gid))));
      });
    }
    var reach = reachForUser(u);
    body.appendChild(label("Can reach (" + reach.length + " objects)"));
    if (!reach.length) body.appendChild(h("div", { class: "panel-sub", style: "padding:6px 0;" }, "No explicitly-shared objects in this slice."));
    reach.slice(0, 200).forEach(function (r) {
      body.appendChild(h("div", { class: "grant" },
        h("span", { class: "gkind" }, r.via),
        h("span", { class: "gname" }, link("object", r.obj.uid, name(r.obj))),
        accessChip(r.access)));
    });
    box.appendChild(body);
    return box;
  }
  function reachForUser(u) {
    var seen = {}, out = [];
    (sharesToPrincipal[u.uid] || []).forEach(function (s) {
      if (s.principal_kind === "user" && objByUid[s.object_uid]) { seen[s.object_uid] = 1; out.push({ obj: objByUid[s.object_uid], access: s.access, via: "direct" }); }
    });
    (groupsByUser[u.uid] || []).forEach(function (gid) {
      (sharesToPrincipal[gid] || []).forEach(function (s) {
        if (s.principal_kind === "group" && objByUid[s.object_uid] && !seen[s.object_uid]) {
          seen[s.object_uid] = 1; out.push({ obj: objByUid[s.object_uid], access: s.access, via: "group" });
        }
      });
    });
    return out.sort(function (a, b) { return name(a.obj).localeCompare(name(b.obj)); });
  }

  function groupDetail(box, g) {
    if (!g) { box.appendChild(h("div", { class: "empty" }, "Group not in graph.")); return box; }
    head(box, "User group", name(g));
    var body = h("div", { class: "dbody" });
    body.appendChild(kvRow("UID", g.uid));
    body.appendChild(kvRow("Members", String(g.member_count || 0)));
    var reach = (sharesToPrincipal[g.uid] || []).filter(function (s) { return s.principal_kind === "group" && objByUid[s.object_uid]; });
    body.appendChild(label("Shared objects (" + reach.length + ")"));
    reach.sort(function (a, b) { return name(objByUid[a.object_uid]).localeCompare(name(objByUid[b.object_uid])); })
      .slice(0, 200).forEach(function (s) {
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" }, objByUid[s.object_uid].type),
          h("span", { class: "gname" }, link("object", s.object_uid, name(objByUid[s.object_uid]))),
          accessChip(s.access)));
      });
    var members = membersByGroup[g.uid] || [];
    if (members.length) {
      body.appendChild(label("Members (" + members.length + ")"));
      members.slice(0, 200).forEach(function (uid) {
        var u = userByUid[uid];
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" + (u && u.superuser ? " " : "") }, u && u.superuser ? "super" : "user"),
          h("span", { class: "gname" }, link("user", uid, u ? name(u) : uid))));
      });
    }
    box.appendChild(body);
    return box;
  }

  function roleDetail(box, r) {
    if (!r) { box.appendChild(h("div", { class: "empty" }, "Role not in graph.")); return box; }
    head(box, "User role" + (r.grants_all ? " · grants ALL" : ""), name(r));
    var body = h("div", { class: "dbody" });
    body.appendChild(kvRow("UID", r.uid));
    body.appendChild(kvRow("Grants ALL (superuser)", r.grants_all ? "yes" : "no"));
    body.appendChild(kvRow("Members", String(r.member_count || 0)));
    var members = usersByRole[r.uid] || [];
    if (members.length) {
      body.appendChild(label("Held by (" + members.length + ")"));
      members.slice(0, 200).forEach(function (uid) {
        var u = userByUid[uid];
        body.appendChild(h("div", { class: "grant" },
          h("span", { class: "gkind" }, "user"),
          h("span", { class: "gname" }, link("user", uid, u ? name(u) : uid))));
      });
    }
    var auth = r.authorities || [];
    if (auth.length) {
      body.appendChild(label("Authorities (" + auth.length + ")"));
      body.appendChild(h("div", { class: "panel-sub", style: "line-height:1.7;word-break:break-word;" }, auth.join(", ")));
    }
    box.appendChild(body);
    return box;
  }

  // ---- caveats -----------------------------------------------------------------
  function renderCaveats() {
    var box = h("div", { class: "caveats" }, h("h4", {}, "Honesty boundaries"));
    var ul = h("ul", {});
    (G.caveats || []).forEach(function (c) { ul.appendChild(h("li", {}, c)); });
    box.appendChild(ul);
    return box;
  }

  // ---- d3 severity distribution bar -------------------------------------------
  function severityChart() {
    var order = ["high", "med", "low", "none"];
    var colorVar = { high: "--high", med: "--med", low: "--low", none: "--none" };
    var counts = { high: 0, med: 0, low: 0, none: 0 };
    G.objects.forEach(function (o) { counts[exposure(o).sev]++; });
    var total = G.objects.length || 1;
    var wrap = h("div", { class: "chart-row" });
    var width = 100;
    var svg = d3.create("svg").attr("viewBox", "0 0 " + width + " 12").attr("width", "100%").attr("height", 16)
      .attr("preserveAspectRatio", "none").attr("role", "img").attr("aria-label", "Exposure distribution");
    var x = 0;
    order.forEach(function (k) {
      var w = (counts[k] / total) * width;
      if (w <= 0) return;
      svg.append("rect").attr("x", x).attr("y", 0).attr("width", w).attr("height", 12)
        .attr("fill", "var(" + colorVar[k] + ")").append("title").text(k + ": " + counts[k]);
      x += w;
    });
    wrap.appendChild(svg.node());
    var legend = h("div", { class: "legend" }, order.filter(function (k) { return counts[k]; }).map(function (k) {
      return h("span", {}, h("i", { style: "background:var(" + colorVar[k] + ");" }), k + " " + counts[k]);
    }));
    wrap.appendChild(legend);
    return wrap;
  }

  // ---- boot --------------------------------------------------------------------
  applyHash();
  render();
})();
