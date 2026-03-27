const state = {
  payload: null,
  view: "library",
};

const titles = {
  library: ["Library", "Browse the local AutoBook catalog."],
  analytics: ["Analytics", "View local reading and catalog distribution."],
  history: ["History", "Inspect recent download events."],
  devices: ["Transfers", "Inspect recent device transfer events."],
};

function setHeader() {
  const [title, subtitle] = titles[state.view];
  document.getElementById("view-title").textContent = title;
  document.getElementById("view-subtitle").textContent = subtitle;
}

function renderStats() {
  const stats = document.getElementById("stats");
  const payload = state.payload;
  if (!payload) return;
  const items = [
    ["Books", payload.analytics.total_books],
    ["Favorites", payload.analytics.favorites],
    ["Collections", payload.analytics.collections],
    ["Tags", payload.analytics.tags],
  ];
  stats.innerHTML = items.map(([label, value]) => `<div class="stat"><div class="label">${label}</div><div class="value">${value}</div></div>`).join("");
}

function renderLibrary(filter = "") {
  const books = (state.payload?.books || []).filter((book) =>
    !filter || `${book.title} ${book.author} ${book.summary}`.toLowerCase().includes(filter.toLowerCase())
  );
  return `<div class="grid">${books.map((book) => `
    <article class="card">
      <h3>${book.title}</h3>
      <p>${book.author || ""}</p>
      <p>${book.summary || ""}</p>
    </article>`).join("")}</div>`;
}

function renderBars(values) {
  const entries = Object.entries(values || {});
  if (!entries.length) return `<div class="list-item"><p>No data yet.</p></div>`;
  const top = Math.max(...entries.map(([, count]) => count), 1);
  return `<div class="bars">${entries.map(([label, count]) => `
    <div class="bar-row">
      <div>${label}</div>
      <div class="bar"><span style="width:${(count / top) * 100}%"></span></div>
      <div>${count}</div>
    </div>`).join("")}</div>`;
}

function renderAnalytics() {
  const analytics = state.payload?.analytics || {};
  return `
    <div class="card">
      <h3>By Source</h3>
      ${renderBars(analytics.by_source)}
    </div>
    <div class="card">
      <h3>By Format</h3>
      ${renderBars(analytics.by_format)}
    </div>
    <div class="card">
      <h3>By Reading Status</h3>
      ${renderBars(analytics.by_status)}
    </div>
  `;
}

function renderList(items, formatter) {
  if (!items.length) return `<div class="list-item"><p>No items.</p></div>`;
  return `<div class="list">${items.map(formatter).join("")}</div>`;
}

function renderHistory() {
  return renderList(state.payload?.download_history || [], (item) => `
    <article class="list-item">
      <strong>${item.title}</strong>
      <p>${item.timestamp} | ${item.source} | ${item.status}</p>
      <p>${item.message || ""}</p>
    </article>
  `);
}

function renderTransfers() {
  return renderList(state.payload?.transfer_history || [], (item) => `
    <article class="list-item">
      <strong>${item.title}</strong>
      <p>${item.timestamp} | ${item.device_name} | ${item.status}</p>
      <p>${item.message || ""}</p>
    </article>
  `);
}

function renderView() {
  const view = document.getElementById("view");
  const filter = document.getElementById("search").value || "";
  setHeader();
  if (state.view === "library") view.innerHTML = renderLibrary(filter);
  if (state.view === "analytics") view.innerHTML = renderAnalytics();
  if (state.view === "history") view.innerHTML = renderHistory();
  if (state.view === "devices") view.innerHTML = renderTransfers();
}

async function loadPayload() {
  const response = await fetch("/api/payload");
  state.payload = await response.json();
  renderStats();
  renderView();
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.view = button.dataset.view;
    renderView();
  });
});

document.getElementById("search").addEventListener("input", () => {
  if (state.view === "library") renderView();
});

loadPayload();
