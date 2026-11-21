/* Ye Pesare · Glass Panel — live renderer (filters, search, count-up) */
"use strict";

const $ = (id) => document.getElementById(id);
/* Persian digits built from codepoints (safe against editor mangling) */
const FA = Array.from({ length: 10 }, (_, i) => String.fromCharCode(0x06f0 + i));
const fa = (n) => String(n ?? "").replace(/\d/g, (d) => FA[+d]);

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

const T = {
  noProjects: "هیچ پروژه‌ای هنوز ثبت نشده — با <code>/new_project</code> در تلگرام اولین رو بسازید.",
  noFilter: "موردی با این فیلتر پیدا نشد 🤷",
  noTasks: "✅ تسکی باقی نمونده",
  noTeam: "هنوز کسی ثبت‌نام نکرده — <code>/join</code>",
  noIdeas: "💡 هنوز ایده‌ای ثبت نشده",
  noActivity: "هیچ فعالیتی ثبت نشده",
  calm: "همه‌چیز آرومه ✅",
  noNear: "ددلاین نزدیکی ثبت نشده",
  daysWord: "روز",
  today: "امروز",
  proj: "پروژه",
  member: "نفر",
  all: "همه",
  refresh: "بروزرسانی",
};

const state = { filter: "all", q: "", countdown: 30, timer: null, tick: null };

/* ── count-up animation for stat numbers ── */
function setNum(el, v) {
  if (!el) return;
  const from = parseInt(el.dataset.v || "0", 10);
  if (from === v) { el.textContent = fa(v); return; }
  el.dataset.v = v;
  const t0 = performance.now(), dur = 650;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = fa(Math.round(from + (v - from) * e));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ── filter chips ── */
function renderChips(projects) {
  const box = $("projectFilters");
  const counts = new Map();
  projects.forEach((p) => counts.set(p.status_key, (counts.get(p.status_key) || 0) + 1));
  const order = [...counts.keys()];
  const chip = (key, label, n) =>
    `<button class="chip ${state.filter === key ? "on" : ""}" data-f="${esc(key)}">${label}${n ? ` ${fa(n)}` : ""}</button>`;
  box.innerHTML =
    chip("all", T.all, projects.length) +
    order.map((k) => {
      const meta = projects.find((p) => p.status_key === k).status;
      return chip(k, `${meta.emoji} ${esc(meta.label)}`, counts.get(k));
    }).join("");
}

function visibleProjects(projects) {
  const q = state.q.trim().toLowerCase();
  return projects.filter((p) => {
    if (state.filter !== "all" && p.status_key !== state.filter) return false;
    if (q && !(`${p.title} ${p.description || ""}`.toLowerCase().includes(q))) return false;
    return true;
  });
}

/* ── project cards ── */
function renderProjects(projects) {
  const shown = visibleProjects(projects);
  renderChips(projects);
  $("projCount").textContent = `${fa(projects.length)} ${T.proj}` +
    (shown.length !== projects.length ? ` · ${fa(shown.length)} نمایش` : "");

  if (!projects.length) {
    $("projectsGrid").innerHTML =
      `<div class="empty"><span class="e-emoji">🌱</span>${T.noProjects}</div>`;
    return;
  }
  if (!shown.length) {
    $("projectsGrid").innerHTML = `<div class="empty"><span class="e-emoji">🔍</span>${T.noFilter}</div>`;
    return;
  }

  $("projectsGrid").innerHTML = shown.map((p) => {
    let badge = "";
    if (p.overdue > 0) badge = `<span class="pc-badge late">⛔ ${fa(p.overdue)}</span>`;
    else if (p.due_soon > 0) badge = `<span class="pc-badge due">⚡ ${fa(p.due_soon)}</span>`;
    else if (p.progress === 100 && p.tasks_total > 0) badge = `<span class="pc-badge ok">✅ کامل</span>`;
    const risk = p.overdue > 0 ? " risk" : "";
    return `
    <div class="project-card${risk}">
      <div class="pc-top">
        <div>
          <div class="pc-title">${p.type.emoji} ${esc(p.title)}</div>
          <div class="pc-type">${esc(p.type.label)}</div>
        </div>
        <span class="status-pill s-${esc(p.status_key)}">${p.status.emoji} ${esc(p.status.label)}</span>
      </div>
      <div class="pc-desc">${esc(p.description || "—")}</div>
      <div class="bar" title="پیشرفت"><i style="width:${p.progress}%"></i></div>
      <div class="pc-foot">
        <span>🧩 <bdi>${fa(p.tasks_done)}/${fa(p.tasks_total)}</bdi> ${fa(p.progress)}٪</span>
        ${badge}${p.nag_days != null ? `<span class="pc-badge cyc">🔁 ${p.nag_days === 0 ? "خاموش" : "هر " + fa(p.nag_days) + " روز"}</span>` : ""}
        <span class="tone-${p.deadline_meta.tone}">⏰ <bdi>${esc(p.deadline)}</bdi> · ${esc(p.deadline_meta.label)}</span>
      </div>
    </div>`;
  }).join("");
}

/* ── next deadline ── */
function renderNext(d) {
  const nd = d.next_deadline, box = $("nextDeadline");
  if (nd) {
    const days = nd.deadline_meta.days;
    $("ndDays").innerHTML = days === 0
      ? `<span>${T.today}</span>`
      : `${fa(days)}<small>${T.daysWord}</small>`;
    box.querySelector(".nd-title").innerHTML = `${nd.type.emoji} ${esc(nd.title)}`;
    box.querySelector(".nd-when").innerHTML =
      `<bdi>${esc(nd.deadline)}</bdi> · <span class="tone-${nd.deadline_meta.tone}">${esc(nd.deadline_meta.label)}</span>`;
  } else {
    $("ndDays").textContent = "✓";
    box.querySelector(".nd-title").textContent = T.calm;
    box.querySelector(".nd-when").textContent = T.noNear;
  }
}

/* ── tasks ── */
function renderTasks(tasks) {
  $("taskList").innerHTML = tasks.map((t) => `
    <li class="task-item">
      <span class="t-emoji">${t.status.emoji}</span>
      <div class="t-body">
        <div class="t-title">${esc(t.title)}</div>
        <div class="t-meta">📁 ${esc(t.project)} · 👤 ${esc(t.assignee)}</div>
      </div>
      <div class="t-right">
        <div><span class="prio-dot p-${esc(t.priority_key)}"></span>${esc(t.priority.label)}</div>
        <div class="tone-${t.deadline.tone}">⏰ <bdi>${esc(t.deadline_disp)}</bdi>${t.deadline_disp !== "—" ? " · " : ""}${esc(t.deadline.label)}</div>
      </div>
    </li>`).join("") || `<li class="activity-item">${T.noTasks}</li>`;
}

/* ── team ── */
const AV = ["", "c-pnk", "c-amb", "c-grn"];
function renderTeam(team) {
  $("teamCount").textContent = `${fa(team.length)} ${T.member}`;
  $("teamList").innerHTML = team.map((m, i) => {
    const pct = m.total ? Math.round(100 * m.done_tasks / m.total) : 0;
    return `
    <li class="team-item">
      <div class="avatar ${AV[i % AV.length]}">${esc(m.avatar)}</div>
      <div>
        <div class="tm-name">${m.is_admin ? "👑 " : ""}${esc(m.name)}</div>
        <div class="tm-role">${esc(m.role.emoji)} ${esc(m.role.label)}${m.username ? " · @" + esc(m.username) : ""}</div>
        <div class="tm-bar"><div class="bar" style="margin-top:5px"><i style="width:${pct}%"></i></div></div>
      </div>
      <div class="tm-tasks"><b>${fa(m.open_tasks)}</b>باز · ${fa(m.done_tasks)} ✅</div>
    </li>`;
  }).join("") || `<li class="activity-item">${T.noTeam}</li>`;
}

/* ── ideas / activity ── */
function renderIdeas(ideas) {
  $("ideaList").innerHTML = ideas.map((i) => `
    <li class="idea-item">
      <div class="idea-cat">${i.category.emoji} ${esc(i.category.label)}</div>
      ${esc(i.content)}
    </li>`).join("") || `<li class="activity-item">${T.noIdeas}</li>`;
}

function renderActivity(acts) {
  $("activityList").innerHTML = acts.map((a) => `
    <li class="activity-item">
      <span class="ac-dot"></span>
      <div>
        <span class="ac-who">${esc(a.who)}</span>
        <span class="ac-time">· ${esc(a.at_disp || "")}</span>
        <div class="ac-detail">${esc(a.detail || a.action)}</div>
      </div>
    </li>`).join("") || `<li class="activity-item">${T.noActivity}</li>`;
}

/* ── master render ── */
function render(d) {
  setNum($("stProjects"), d.stats.projects);
  setNum($("stTasks"), d.stats.tasks);
  setNum($("stTasksDone"), d.stats.tasks_done);
  setNum($("stDueSoon"), d.stats.due_soon ?? 0);
  setNum($("stOverdue"), d.stats.overdue ?? 0);
  setNum($("stMembers"), d.stats.members);
  setNum($("stIdeas"), d.stats.ideas);
  $("updatedAt").textContent = d.updated_at_disp || d.updated_at || "—";
  renderNext(d);
  renderProjects(d.projects);
  renderTasks(d.tasks);
  renderTeam(d.team);
  renderIdeas(d.ideas);
  renderActivity(d.activity);
}

/* ── loading + auto refresh ── */
async function load(manual) {
  const btn = $("refreshBtn");
  if (manual) btn.classList.add("spin");
  try {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), 9000);
    const res = await fetch("/api/dashboard", { signal: ctl.signal });
    clearTimeout(to);
    if (!res.ok) throw new Error("HTTP " + res.status);
    render(await res.json());
    $("netErr").hidden = true;
  } catch (e) {
    console.error("dashboard load failed", e);
    $("netErr").hidden = false;
  } finally {
    if (manual) setTimeout(() => btn.classList.remove("spin"), 450);
    state.countdown = 30;
  }
}

function bind() {
  $("refreshBtn").addEventListener("click", () => load(true));
  $("searchBox").addEventListener("input", (e) => {
    state.q = e.target.value;
    load0();
  });
  $("projectFilters").addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    state.filter = b.dataset.f;
    load0();
  });
  setInterval(() => {
    if (--state.countdown <= 0) load(false);
    else tickLabel();
  }, 1000);
}

/* re-render from last cached payload without refetching (filters/search) */
let last = null;
const _render = render;
render = (d) => { last = d; _render(d); tickLabel(); };
function load0() { if (last) render(last); }
function tickLabel() {
  const el = $("refreshBtn");
  if (!el || el.classList.contains("spin")) return;
  el.title = `${T.refresh} — ${fa(state.countdown)}s`;
}

bind();
load(false);
