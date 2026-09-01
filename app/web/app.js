"use strict";

const LAYER_NAME = {
  technical: "技术质量",
  semantic: "内容语义",
  world_model: "世界模型",
};

const state = {
  dims: [],
  video: null,
  lmm: { base_url: "", api_key: "", model: "" },
  vision: "unknown", // unknown | checking | ok | no_vision
  results: {},
  boardVideos: [],
};

let boardSort = { key: "overall", dir: -1 };

const $ = (id) => document.getElementById(id);

let confirmAction = null;
let restoreScoresToken = 0;

function showModal(msg) {
  $("modalMsg").textContent = msg;
  $("modalCancel").hidden = true;
  confirmAction = null;
  $("modalMask").hidden = false;
}

function showConfirm(msg, onOk) {
  $("modalMsg").textContent = msg;
  $("modalCancel").hidden = false;
  confirmAction = onOk;
  $("modalMask").hidden = false;
}

function lmmReady() {
  return Boolean(state.lmm.base_url && state.lmm.api_key && state.lmm.model);
}

async function postForm(url, data) {
  const body = new FormData();
  for (const [k, v] of Object.entries(data)) body.append(k, v);
  const resp = await fetch(url, { method: "POST", body });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(json.detail || `请求失败 (${resp.status})`);
  return json;
}

async function loadDims() {
  state.dims = await (await fetch("/api/dimensions")).json();
  renderDims();
}

function renderDims() {
  const grid = $("dimsGrid");
  grid.innerHTML = "";
  for (const d of state.dims) {
    const card = document.createElement("div");
    card.className = "dim-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `测试 ${d.dim_id} ${d.name}`);
    card.innerHTML = `
      ${d.needs_vision
        ? '<span class="corner-badge">需视觉模型</span>'
        : '<span class="corner-badge local">本地测试</span>'}
      <span class="dim-id">${d.dim_id}</span>
      <h3>${d.name}</h3>
      <p class="anchor">${d.anchor_mid}</p>
      <span class="layer ${d.layer}">${LAYER_NAME[d.layer]}</span>
      ${state.results[d.dim_id]
        ? `<span class="tested-score">${state.results[d.dim_id].value} 分</span>`
        : ""}`;
    card.addEventListener("click", () => onDimClick(d));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onDimClick(d);
      }
    });
    grid.appendChild(card);
  }
  const n = Object.keys(state.results).length;
  $("testedCount").textContent = `已测 ${n} / ${state.dims.length}`;
}

function setPendingVideo(v, extra) {
  state.video = v;
  $("pendingVideo").hidden = !v;
  $("dropZone").style.display = v ? "none" : "";
  if (v) {
    restoreScores(v.video_id);
    $("pvName").textContent = v.filename || v.video_id;
    $("pvInfo").textContent = extra ||
      `${v.resolution || ""} · ${v.duration_sec || "?"}s · ${v.model_tag || "未标模型"}`;
  } else {
    restoreScoresToken += 1;
    state.results = {};
    renderDims();
  }
}

async function restoreScores(videoId) {
  const token = ++restoreScoresToken;
  state.results = {};
  renderDims();
  try {
    const r = await (await fetch(`/api/scores?video_id=${videoId}`)).json();
    if (token !== restoreScoresToken || state.video?.video_id !== videoId) return;
    state.results = Object.fromEntries(
      Object.entries(r || {}).filter(([, score]) => score.value != null),
    );
    renderDims();
  } catch {
    if (token === restoreScoresToken && state.video?.video_id === videoId) renderDims();
  }
}

async function uploadVideo(file) {
  const data = await postForm("/api/upload", {
    file,
    prompt_text: $("promptText").value.trim(),
    model_tag: $("modelTag").value.trim(),
  });
  if (data.duplicate) {
    setPendingVideo(data, `${data.model_tag || "未标模型"} · 已存在，复用入库记录`);
  } else {
    setPendingVideo(data);
  }
  await loadRecent();
}

async function loadRecent() {
  const list = await (await fetch("/api/videos")).json();
  const wrap = $("recentWrap");
  const el = $("recentList");
  el.innerHTML = "";
  if (!list.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  for (const v of list.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "recent-item";
    const main = document.createElement("button");
    main.className = "ri-main";
    main.textContent = `${v.filename} (${v.resolution || "?"})`;
    main.addEventListener("click", () => setPendingVideo(v));
    const del = document.createElement("button");
    del.className = "ri-del";
    del.title = "删除该视频及评测记录";
    del.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      showConfirm(`删除「${v.filename}」及其评测记录？`, () => deleteVideo(v));
    });
    item.append(main, del);
    el.appendChild(item);
  }
}

async function deleteVideo(v) {
  try {
    const resp = await fetch(`/api/video/${v.video_id}`, { method: "DELETE" });
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}));
      throw new Error(j.detail || `删除失败 (${resp.status})`);
    }
    if (state.video && state.video.video_id === v.video_id) setPendingVideo(null);
    await loadRecent();
  } catch (e) {
    showModal(e.message);
  }
}

function readLmmFromUi() {
  state.lmm = {
    base_url: $("lmmBase").value.trim(),
    api_key: $("lmmKey").value.trim(),
    model: $("lmmModel").value.trim(),
  };
  localStorage.setItem("ve_base", state.lmm.base_url);
  localStorage.setItem("ve_model", state.lmm.model);
  sessionStorage.setItem("ve_key", state.lmm.api_key);
}

function setVisionStatus(st, text) {
  state.vision = st;
  const box = $("visionStatus");
  box.className = `vision-status ${st === "unknown" ? "" : st}`;
  $("visionText").textContent = text;
}

async function checkVision() {
  readLmmFromUi();
  if (!lmmReady()) {
    setVisionStatus("unknown", "未检测");
    return { has_vision: false, missing: true };
  }
  setVisionStatus("checking", "检测中…");
  try {
    const r = await postForm("/api/check-vision", state.lmm);
    if (r.has_vision) setVisionStatus("ok", "已确认视觉能力");
    else setVisionStatus("no_vision", r.reason || "无视觉能力");
    return r;
  } catch (e) {
    setVisionStatus("no_vision", e.message);
    return { has_vision: false, reason: e.message };
  }
}

async function onDimClick(dim) {
  if (!state.video) { showModal("请提供测试视频"); return; }
  if (!dim.needs_vision) { openDim(dim); return; }
  readLmmFromUi();
  if (!lmmReady()) { showModal("请提供测试用视觉模型"); return; }
  if (state.vision === "no_vision") { showModal("请更换有视觉能力的模型API"); return; }
  if (state.vision !== "ok") {
    const r = await checkVision();
    if (!r.has_vision) {
      showModal(r.missing ? "请提供测试用视觉模型" : "请更换有视觉能力的模型API");
      return;
    }
  }
  openDim(dim);
}

let currentDim = null;

function openDim(dim) {
  currentDim = dim;
  $("viewHome").hidden = true;
  $("viewDim").hidden = false;
  $("dimLayer").textContent = LAYER_NAME[dim.layer];
  $("dimLayer").className = `layer-chip layer ${dim.layer}`;
  $("dimTitle").textContent = `${dim.dim_id} ${dim.name}`;
  $("dimAnchors").innerHTML = ["low", "mid", "high"].map((k) => `
    <div><dt>${{low: "低分锚点", mid: "中分锚点", high: "高分锚点"}[k]}</dt>
    <dd>${dim["anchor_" + k]}</dd></div>`).join("");
  $("dimNeed").textContent = dim.needs_vision
    ? "本维度需要视觉大模型，测试将调用你配置的 API。"
    : "本维度为本地测试，无需 API。";
  $("dimPlayer").src = `/api/video/${state.video.video_id}/file`;
  const prev = state.results[dim.dim_id];
  $("dimResult").hidden = !prev;
  if (prev) renderResult(prev);
  window.scrollTo(0, 0);
}

function renderResult(r) {
  $("dimResult").hidden = false;
  $("scoreNum").textContent = r.value == null ? "--" : r.value;
  $("scoreBar").style.width = `${(r.value || 0) * 10}%`;
  $("methodChip").textContent = r.method === "objective" && r.note?.startsWith("本地信号")
    ? "本地信号指标" : "视觉大模型";
  $("scoreNote").textContent = r.note || "";
}

async function runTest() {
  if (!state.video) { showModal("请提供测试视频"); return; }
  const dim = currentDim;
  if (dim.needs_vision) {
    readLmmFromUi();
    if (!lmmReady()) { showModal("请提供测试用视觉模型"); return; }
  }
  const btn = $("btnRun");
  btn.disabled = true;
  $("dimLoading").hidden = false;
  $("dimResult").hidden = true;
  try {
    const r = await postForm(`/api/evaluate/${dim.dim_id}`, {
      video_id: state.video.video_id,
      prompt_text: $("promptText").value.trim(),
      ...state.lmm,
    });
    state.results[dim.dim_id] = r;
    renderResult(r);
    renderDims();
  } catch (e) {
    showModal(e.message.includes("请提供测试用视觉模型")
      ? "请提供测试用视觉模型" : e.message);
  } finally {
    btn.disabled = false;
    $("dimLoading").hidden = true;
  }
}

function showView(view) {
  $("viewHome").hidden = true;
  $("viewBoard").hidden = true;
  $("viewDim").hidden = true;
  $("viewWork").hidden = true;
  $("viewIntro").hidden = true;
  if (view === "home") $("viewHome").hidden = false;
  else if (view === "board") {
    $("viewBoard").hidden = false;
    loadDashboard();
  } else if (view === "work") {
    $("viewWork").hidden = false;
    loadWorkbench();
  } else if (view === "intro") {
    $("viewIntro").hidden = false;
  }
  document.querySelectorAll(".nav-tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view));
  window.scrollTo(0, 0);
}

function fmt(v) {
  return v == null ? "—" : Number(v).toFixed(1);
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function cellClass(v) {
  if (v == null) return "";
  if (v >= 8) return "good";
  if (v >= 6) return "ok";
  if (v >= 4) return "warn";
  return "bad";
}

async function loadDashboard() {
  try {
    const d = await (await fetch("/api/dashboard")).json();
    state.boardVideos = d.videos || [];
    const s = d.summary || {};
    $("boardSummary").textContent = s.n_videos
      ? `共 ${s.n_videos} 个视频 · ${s.n_ratings} 条评分 · 全样本均分 ${fmt(s.overall_mean)}`
      : "暂无评测数据，先去主页测几个视频吧。";
    renderRadar(d.videos || []);
    renderHist(d.mos_hist || []);
    renderModelBoard(d.models || []);
    renderLeaderboard();
    renderWorldBoard(d.world_model || []);
  } catch (e) {
    showModal("看板加载失败：" + e.message);
  }
}

function renderRadar(videos) {
  const wrap = $("radarWrap");
  if (!videos.length || !state.dims.length) {
    wrap.innerHTML = '<p class="hint">暂无评测数据。</p>';
    return;
  }
  const agg = {};
  for (const v of videos) {
    for (const d of state.dims) {
      const val = v.mean_scores[d.dim_id];
      if (val != null) (agg[d.dim_id] = agg[d.dim_id] || []).push(val);
    }
  }
  const vals = state.dims.map((d) =>
    agg[d.dim_id] ? +(agg[d.dim_id].reduce((a, b) => a + b, 0) / agg[d.dim_id].length).toFixed(2) : 0);
  const n = state.dims.length;
  const size = 320, cx = size / 2, cy = size / 2, R = size / 2 - 46;
  const pt = (i, r) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
  };
  let grid = "", axes = "", labels = "";
  for (let g = 1; g <= 4; g++) {
    const rr = (R * g) / 4;
    grid += `<polygon points="${state.dims.map((_, i) => pt(i, rr).join(",")).join(" ")}" fill="none" stroke="#d9e6ff" stroke-width="1"/>`;
  }
  state.dims.forEach((d, i) => {
    const [x, y] = pt(i, R);
    axes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#d9e6ff" stroke-width="1"/>`;
    const [lx, ly] = pt(i, R + 22);
    labels += `<text x="${lx}" y="${ly}" font-size="11" fill="#5b7099" text-anchor="middle" dominant-baseline="middle">${d.dim_id}</text>`;
  });
  const poly = state.dims.map((d, i) => pt(i, R * (vals[i] / 10)).join(",")).join(" ");
  wrap.innerHTML = `<svg viewBox="0 0 ${size} ${size}" width="100%" style="max-width:360px;display:block;margin:0 auto">
    ${grid}${axes}
    <polygon points="${poly}" fill="rgba(37,99,235,0.22)" stroke="#2563eb" stroke-width="2"/>
    ${state.dims.map((d, i) => { const [x, y] = pt(i, R * (vals[i] / 10)); return `<circle cx="${x}" cy="${y}" r="3" fill="#2563eb"/>`; }).join("")}
    ${labels}
  </svg>
  <p class="hint" style="text-align:center">全样本 ${n} 维均值轮廓</p>`;
}

function renderHist(hist) {
  const wrap = $("histWrap");
  if (!hist.length) { wrap.innerHTML = '<p class="hint">暂无评分。</p>'; return; }
  const max = Math.max(1, ...hist.map((h) => h.count));
  const w = 460, h = 200, pad = 28;
  const bw = (w - pad * 2) / hist.length;
  let bars = "";
  hist.forEach((hst, i) => {
    const bh = (hst.count / max) * (h - pad * 2);
    const x = pad + i * bw, y = h - pad - bh;
    bars += `<rect x="${x + 2}" y="${y}" width="${bw - 4}" height="${bh}" fill="#3b82f6" rx="2"/>`;
    if (hst.count) bars += `<text x="${x + bw / 2}" y="${y - 4}" font-size="10" fill="#5b7099" text-anchor="middle">${hst.count}</text>`;
    bars += `<text x="${x + bw / 2}" y="${h - pad + 14}" font-size="9" fill="#5b7099" text-anchor="middle">${hst.bin}</text>`;
  });
  wrap.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="100%" style="max-width:480px;display:block;margin:0 auto">
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#d9e6ff"/>
    ${bars}
  </svg>`;
}

function renderModelBoard(models) {
  const wrap = $("modelBoard");
  if (!models.length) { wrap.innerHTML = '<p class="hint">暂无数据。</p>'; return; }
  const sorted = [...models].sort((a, b) => (b.overall ?? -1) - (a.overall ?? -1));
  const rows = sorted.map((m, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td>${escapeHtml(m.model_tag)}</td>
      <td class="num">${m.n_videos}</td>
      <td class="num">${fmt(m.layer_means.technical)}</td>
      <td class="num">${fmt(m.layer_means.semantic)}</td>
      <td class="num">${fmt(m.layer_means.world_model)}</td>
      <td class="num strong">${fmt(m.overall)}</td>
    </tr>`).join("");
  wrap.innerHTML = `<table class="lb-table">
    <thead><tr><th class="num">#</th><th>模型</th><th class="num">视频数</th>
    <th class="num">技术均</th><th class="num">语义均</th><th class="num">世界均</th><th class="num">综合</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderLeaderboard() {
  const wrap = $("leaderboard");
  const videos = state.boardVideos || [];
  if (!videos.length) { wrap.innerHTML = '<p class="hint">暂无数据。</p>'; return; }
  const cols = [
    { k: "filename", t: "视频", num: false },
    { k: "model_tag", t: "模型", num: false },
    ...state.dims.map((d) => ({ k: d.dim_id, t: d.dim_id, num: true })),
    { k: "overall", t: "综合", num: true, strong: true },
  ];
  const sorted = [...videos].sort((a, b) => {
    let va, vb;
    if (["overall", "filename", "model_tag"].includes(boardSort.key)) {
      va = a[boardSort.key]; vb = b[boardSort.key];
    } else {
      va = a.mean_scores[boardSort.key]; vb = b.mean_scores[boardSort.key];
    }
    if (va == null) va = -1;
    if (vb == null) vb = -1;
    if (typeof va === "string") return boardSort.dir * String(va).localeCompare(String(vb));
    return boardSort.dir * (va - vb);
  });
  const head = cols.map((c) =>
    `<th data-sort="${c.k}" class="${c.num ? "num" : ""} ${c.strong ? "strong" : ""} ${boardSort.key === c.k ? "sorted" : ""}">${c.t}${boardSort.key === c.k ? (boardSort.dir < 0 ? " ▼" : " ▲") : ""}</th>`).join("");
  const body = sorted.map((v) => {
    const cells = cols.map((c) => {
      if (c.k === "filename") return `<td>${escapeHtml(v.filename)}</td>`;
      if (c.k === "model_tag") return `<td>${escapeHtml(v.model_tag || "未标注")}</td>`;
      if (c.k === "overall") return `<td class="num strong">${fmt(v.overall)}</td>`;
      const val = v.mean_scores[c.k];
      return `<td class="num ${cellClass(val)}">${fmt(val)}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  wrap.innerHTML = `<table class="lb-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  wrap.querySelectorAll("th[data-sort]").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (boardSort.key === k) boardSort.dir *= -1;
    else { boardSort.key = k; boardSort.dir = (k === "filename" || k === "model_tag") ? 1 : -1; }
    renderLeaderboard();
  }));
}

function renderWorldBoard(wm) {
  const wrap = $("worldBoard");
  if (!wm.length) { wrap.innerHTML = '<p class="hint">暂无数据。</p>'; return; }
  const w = 560, h = 240, pad = 36;
  const groups = wm.length, dims = ["D08", "D09", "D10"];
  const colors = { D08: "#2563eb", D09: "#0891b2", D10: "#4f46e5" };
  const gw = (w - pad * 2) / groups, bw = gw / 4;
  let bars = "";
  wm.forEach((v, i) => {
    const gx = pad + i * gw;
    dims.forEach((dim, j) => {
      const val = v[dim];
      const bh = val == null ? 0 : (val / 10) * (h - pad * 2);
      const x = gx + 8 + j * bw, y = h - pad - bh;
      bars += `<rect x="${x}" y="${y}" width="${bw - 3}" height="${bh}" fill="${colors[dim]}" rx="2"><title>${dim}: ${fmt(val)}</title></rect>`;
    });
    const label = v.filename || v.video_id;
    bars += `<text x="${gx + gw / 2}" y="${h - pad + 14}" font-size="10" fill="#5b7099" text-anchor="middle">${escapeHtml(label.length > 8 ? label.slice(0, 8) + "…" : label)}</text>`;
  });
  const legend = dims.map((dim) =>
    `<span class="lg"><i style="background:${colors[dim]}"></i>${dim}</span>`).join("");
  const yticks = [0, 2, 4, 6, 8, 10].map((t) =>
    `<text x="${pad - 6}" y="${h - pad - (t / 10) * (h - pad * 2)}" font-size="9" fill="#5b7099" text-anchor="end" dominant-baseline="middle">${t}</text>`).join("");
  wrap.innerHTML = `<div class="legend">${legend}</div><svg viewBox="0 0 ${w} ${h}" width="100%" style="max-width:560px;display:block;margin:0 auto">
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#d9e6ff"/>
    ${yticks}${bars}</svg>`;
}

async function loadWorkbench() {
  try {
    const list = await (await fetch("/api/videos")).json();
    const sel = $("wbVideo");
    sel.innerHTML = list.length
      ? list.map((v) => `<option value="${v.video_id}">${escapeHtml(v.filename)} (${v.model_tag || "未标模型"})</option>`).join("")
      : `<option value="">（暂无视频，请先去主页上传）</option>`;
    buildSliders();
    await loadReliability();
  } catch (e) {
    showModal("工作台加载失败：" + e.message);
  }
}

function buildSliders() {
  const wrap = $("wbSliders");
  const groups = {
    technical: "技术质量",
    semantic: "内容语义",
    world_model: "世界模型 / 内在真实性",
  };
  let html = "";
  for (const [layer, title] of Object.entries(groups)) {
    const ds = state.dims.filter((d) => d.layer === layer);
    if (!ds.length) continue;
    html += `<div class="wb-group"><h3>${title}</h3>`;
    for (const d of ds) {
      html += `<div class="wb-row">
        <span class="wb-dim">${d.dim_id} ${d.name}</span>
        <input type="range" min="0" max="10" step="0.5" value="5" data-dim="${d.dim_id}" class="wb-range">
        <span class="wb-val" id="wbval_${d.dim_id}">5.0</span>
        <select class="wb-gate" data-dim="${d.dim_id}" aria-label="${d.dim_id} 低分原因" disabled>
          <option value="na">不适用</option>
          <option value="technical">技术失真</option>
          <option value="semantic">语义错位</option>
          <option value="physical">物理/常识错误</option>
        </select>
        <span class="wb-anchor">低:${d.anchor_low} → 高:${d.anchor_high}</span>
      </div>`;
    }
    html += `</div>`;
  }
  wrap.innerHTML = html;
  wrap.querySelectorAll(".wb-range").forEach((el) => {
    el.addEventListener("input", () => {
      $("wbval_" + el.dataset.dim).textContent = Number(el.value).toFixed(1);
      const row = el.closest(".wb-row");
      const gate = row.querySelector(".wb-gate");
      const low = Number(el.value) <= 4;
      row.classList.toggle("low", low);
      gate.disabled = !low;
      if (!low) gate.value = "na";
    });
  });
}

async function submitWorkbench() {
  const videoId = $("wbVideo").value;
  if (!videoId) { showModal("请先去主页上传视频"); return; }
  const dims = {};
  $("wbSliders").querySelectorAll(".wb-range").forEach((el) => {
    dims[el.dataset.dim] = parseFloat(el.value);
  });
  const gates = {};
  for (const el of $("wbSliders").querySelectorAll(".wb-range")) {
    const gate = document.querySelector(`.wb-gate[data-dim="${el.dataset.dim}"]`).value;
    gates[el.dataset.dim] = gate;
    if (dims[el.dataset.dim] > 4) continue;
    const dim = state.dims.find((d) => d.dim_id === el.dataset.dim);
    const expected = dim.layer === "world_model" ? "physical" : dim.layer;
    if (gate !== expected) {
      showModal(`${el.dataset.dim} 是低分，请选择「${expected === "physical" ? "物理/常识错误" : expected === "technical" ? "技术失真" : "语义错位"}」`);
      return;
    }
  }
  const payload = {
    video_id: videoId,
    role: $("wbRole").value,
    rater_id: ($("wbRater").value.trim() || (($("wbRole").value === "expert" ? "expert" : "user") + "_anon")),
    dims, gate: "na", gates,
    note: $("wbNote").value.trim(),
  };
  const btn = $("wbSubmit");
  btn.disabled = true;
  $("wbSaveMsg").textContent = "保存中…";
  try {
    const resp = await fetch("/api/score/subjective", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(j.detail || `保存失败 (${resp.status})`);
    $("wbSaveMsg").textContent = "✓ " + (j.detail || "已保存") + " — 可切到数据看板查看";
    await loadReliability();
  } catch (e) {
    $("wbSaveMsg").textContent = "✗ " + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function loadReliability() {
  const wrap = $("reliability");
  try {
    const rows = await (await fetch("/api/reliability")).json();
    if (!rows.length) { wrap.innerHTML = '<p class="hint">暂无数据。</p>'; return; }
    const body = rows.map((r) => {
      const icc = r.icc == null ? "样本不足" : r.icc;
      const al = r.krippendorff_alpha == null ? "样本不足" : r.krippendorff_alpha;
      const warnIcc = r.icc != null && r.icc < 0.6;
      const warnAl = r.krippendorff_alpha != null && r.krippendorff_alpha < 0.667;
      return `<tr>
        <td>${r.dim_id} ${r.name}</td>
        <td class="num ${warnIcc ? "bad" : ""}">${icc}</td>
        <td class="num ${warnAl ? "bad" : ""}">${al}</td>
      </tr>`;
    }).join("");
    wrap.innerHTML = `<table class="lb-table"><thead><tr><th>维度</th><th class="num">ICC(2,1)</th><th class="num">Krippendorff's α</th></tr></thead><tbody>${body}</tbody></table>`;
  } catch (e) {
    wrap.innerHTML = `<p class="hint">一致性加载失败：${escapeHtml(e.message)}</p>`;
  }
}

function exportVbench() {
  window.location.href = "/api/export/vbench";
}

function init() {
  $("lmmBase").value = localStorage.getItem("ve_base") || "";
  $("lmmModel").value = localStorage.getItem("ve_model") || "";
  $("lmmKey").value = sessionStorage.getItem("ve_key") || "";

  $("videoInput").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadVideo(e.target.files[0]);
  });
  const dz = $("dropZone");
  ["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => {
    e.preventDefault(); dz.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => {
    e.preventDefault(); dz.classList.remove("dragover");
  }));
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) uploadVideo(f);
  });
  $("pvRemove").addEventListener("click", () => setPendingVideo(null));
  $("btnCheckVision").addEventListener("click", checkVision);
  $("btnBack").addEventListener("click", () => showView("home"));
  $("btnRun").addEventListener("click", runTest);
  $("wbSubmit").addEventListener("click", submitWorkbench);
  $("wbExport").addEventListener("click", exportVbench);
  $("modalOk").addEventListener("click", () => {
    $("modalMask").hidden = true;
    if (confirmAction) { const a = confirmAction; confirmAction = null; a(); }
  });
  $("modalCancel").addEventListener("click", () => { $("modalMask").hidden = true; });
  $("modalMask").addEventListener("click", (e) => {
    if (e.target === $("modalMask")) $("modalMask").hidden = true;
  });
  document.querySelectorAll(".nav-tab").forEach((b) =>
    b.addEventListener("click", () => showView(b.dataset.view)));

  loadDims().then(loadRecent);
}

init();
