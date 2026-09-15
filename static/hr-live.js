function emptyFeedText(p) {
  if (!p.clocked_in) return "Clocked out — camera off";
  if (p.camera_blocked) return "Camera blocked on their PC";
  if (!p.agent_live) return "Waiting for agent";
  return "Waiting for camera";
}

function ensureCard(root, p) {
  let el = root.querySelector(`[data-person="${p.id}"]`);
  if (el) return el;
  el = document.createElement("a");
  el.className = "card person";
  el.dataset.person = String(p.id);
  el.innerHTML = `
    <header>
      <div>
        <h2></h2>
        <p class="muted person-dept"></p>
      </div>
      <span class="person-badge"></span>
    </header>
    <div class="person-feed-wrap">
      <img class="person-feed" alt="Live desk overlay" data-id="${p.id}">
      <p class="person-feed-empty">Waiting for camera</p>
    </div>
    <div class="person-rows">
      <div class="now-row"><span>App</span><b class="person-app"></b></div>
      <div class="now-row"><span>Today</span><b class="person-today"></b></div>
    </div>
    <p class="now-ago"></p>`;
  root.appendChild(el);
  return el;
}

function fillCard(el, p) {
  el.href = `/hr/employee/${p.id}`;
  el.querySelector("h2").textContent = p.name;
  el.querySelector(".person-dept").textContent = `${p.department} · ${p.device || "no device"}`;
  el.querySelector(".person-badge").innerHTML = badge(p.status);
  const app = el.querySelector(".person-app");
  app.textContent = p.app || "—";
  app.title = p.app || "";
  el.querySelector(".person-today").textContent =
    `seated ${p.today.seated} · break ${p.today.break_left || "30m"}`;
  el.querySelector(".now-ago").textContent = ago(p.updated);
  el.querySelector(".person-feed-empty").textContent = emptyFeedText(p);
}

async function refresh() {
  const res = await fetch("/api/team");
  if (!res.ok) return;
  const data = await res.json();
  const c = data.counts;
  const hours = document.getElementById("hours");
  if (hours) {
    hours.hidden = !!data.work_hours;
  }
  document.getElementById("kpis").innerHTML = `
    <div class="kpi"><span>Present</span><strong>${c.present || 0}</strong></div>
    <div class="kpi"><span>Away</span><strong>${c.away || 0}</strong></div>
    <div class="kpi"><span>Idle</span><strong>${c.idle || 0}</strong></div>
    <div class="kpi"><span>Break</span><strong>${c.break || 0}</strong></div>
    <div class="kpi"><span>Clocked out</span><strong>${c["clocked-out"] || 0}</strong></div>
    <div class="kpi"><span>Offline</span><strong>${c.offline || 0}</strong></div>`;

  document.getElementById("alerts").innerHTML = data.alerts
    .filter((a) => !a.seen)
    .map((a) => `<div class="alert">
      <div><strong>HR ping</strong> ${esc(a.message)}</div>
      <button onclick="ack(${a.id})">Got it</button>
    </div>`).join("");

  const root = document.getElementById("team");
  const seen = new Set();
  data.team.forEach((p) => {
    seen.add(String(p.id));
    const el = ensureCard(root, p);
    fillCard(el, p);
  });
  [...root.children].forEach((el) => {
    if (!seen.has(el.dataset.person)) el.remove();
  });
}

function refreshFeeds() {
  document.querySelectorAll(".person-feed").forEach((img) => {
    const id = img.dataset.id;
    const url = `/api/hr/preview/${id}?` + Date.now();
    const empty = img.parentElement.querySelector(".person-feed-empty");
    const probe = new Image();
    probe.onload = () => {
      img.src = url;
      img.style.display = "block";
      if (empty) empty.style.display = "none";
    };
    probe.onerror = () => {
      img.style.display = "none";
      if (empty) empty.style.display = "flex";
    };
    probe.src = url;
  });
}

async function ack(id) {
  await fetch(`/api/alerts/${id}/seen`, { method: "POST" });
  refresh();
}

refresh();
refreshFeeds();
setInterval(refresh, 3000);
setInterval(refreshFeeds, 600);
