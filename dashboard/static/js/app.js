/* Ye Pesare · Glass Panel — live data renderer */
const $ = (id) => document.getElementById(id);

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

async function load() {
  try {
    const res = await fetch("/api/dashboard");
    const d = await res.json();
    render(d);
  } catch (e) {
    console.error("dashboard load failed", e);
  }
}

function render(d) {
  // stats
  $("stProjects").textContent = d.stats.projects;
  $("stTasks").textContent = d.stats.tasks;
  $("stTasksDone").textContent = d.stats.tasks_done;
  $("stMembers").textContent = d.stats.members;
  $("stIdeas").textContent = d.stats.ideas;
  $("updatedAt").textContent = (d.updated_at || "").replace("T", " ").slice(0, 16) + " UTC";

  // next deadline
  const nd = d.next_deadline;
  const ndBox = $("nextDeadline");
  if (nd) {
    ndBox.querySelector(".nd-title").innerHTML =
      `${nd.type.emoji} ${esc(nd.title)}`;
    ndBox.querySelector(".nd-when").innerHTML =
      `${esc(nd.deadline)} · <span class="tone-${nd.deadline_meta.tone}">${esc(nd.deadline_meta.label)}</span>`;
  } else {
    ndBox.querySelector(".nd-title").textContent = "همه‌چیز آرومه ✅";
    ndBox.querySelector(".nd-when").textContent = "ددلاین نزدیکی ثبت نشده";
  }

  // projects
  $("projCount").textContent = `${d.projects.length} پروژه`;
  $("projectsGrid").innerHTML = d.projects.map((p) => `
    <div class="project-card">
      <div class="pc-top">
        <div>
          <div class="pc-title">${p.type.emoji} ${esc(p.title)}</div>
          <div class="pc-type">${esc(p.type.label)}</div>
        </div>
        <span class="status-pill s-${esc(p.status_key)}">${p.status.emoji} ${esc(p.status.label)}</span>
      </div>
      <div class="pc-desc">${esc(p.description || "—")}</div>
      <div class="bar"><i style="width:${p.progress}%"></i></div>
      <div class="pc-foot">
        <span>🧩 ${p.tasks_done}/${p.tasks_total} تسک</span>
        <span class="tone-${p.deadline_meta.tone}">⏰ ${esc(p.deadline_meta.label)}</span>
      </div>
    </div>`).join("");

  // tasks
  $("taskList").innerHTML = d.tasks.map((t) => `
    <li class="task-item">
      <span class="t-emoji">${t.status.emoji}</span>
      <div class="t-body">
        <div class="t-title">${esc(t.title)}</div>
        <div class="t-meta">📁 ${esc(t.project)} · 👤 ${esc(t.assignee)}</div>
      </div>
      <div class="t-right">
        <div>${t.priority.emoji} ${esc(t.priority.label)}</div>
        <div class="tone-${t.deadline.tone}">⏰ ${esc(t.deadline.label)}</div>
      </div>
    </li>`).join("") || `<li class="activity-item">✅ تسکی باقی نمونده</li>`;

  // team
  $("teamCount").textContent = `${d.team.length} نفر`;
  $("teamList").innerHTML = d.team.map((m) => `
    <li class="team-item">
      <div class="avatar">${m.role.emoji}</div>
      <div>
        <div class="tm-name">${esc(m.name)}</div>
        <div class="tm-role">${esc(m.role.label)}${m.username ? " · @" + esc(m.username) : ""}</div>
      </div>
      <div class="tm-tasks"><b>${m.open_tasks}</b>تسک باز</div>
    </li>`).join("");

  // ideas
  $("ideaList").innerHTML = d.ideas.map((i) => `
    <li class="idea-item">
      <div class="idea-cat">${i.category.emoji} ${esc(i.category.label)}</div>
      ${esc(i.content)}
    </li>`).join("") || `<li class="activity-item">💡 هنوز ایده‌ای ثبت نشده</li>`;

  // activity
  $("activityList").innerHTML = d.activity.map((a) => `
    <li class="activity-item">
      <span class="ac-dot"></span>
      <div>
        <span class="ac-who">${esc(a.who)}</span>
        <div class="ac-detail">${esc(a.detail || a.action)}</div>
      </div>
    </li>`).join("") || `<li class="activity-item">—</li>`;
}

load();
setInterval(load, 30000);
