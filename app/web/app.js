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
};

const $ = (id) => document.getElementById(id);

let confirmAction = null;

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
    $("pvName").textContent = v.filename || v.video_id;
    $("pvInfo").textContent = extra ||
      `${v.resolution || ""} · ${v.duration_sec || "?"}s · ${v.model_tag || "未标模型"}`;
  }
}

async function uploadVideo(file) {
  const data = await postForm("/api/upload", {
    file,
    prompt_text: $("promptText").value.trim(),
    model_tag: $("modelTag").value.trim(),
  });
  if (data.duplicate) {
    const full = (await (await fetch("/api/videos")).json())
      .find((v) => v.video_id === data.video_id);
    setPendingVideo(full, `${full.filename} · 已存在，复用入库记录`);
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
  $("btnBack").addEventListener("click", () => {
    $("viewDim").hidden = true;
    $("viewHome").hidden = false;
  });
  $("btnRun").addEventListener("click", runTest);
  $("modalOk").addEventListener("click", () => {
    $("modalMask").hidden = true;
    if (confirmAction) { const a = confirmAction; confirmAction = null; a(); }
  });
  $("modalCancel").addEventListener("click", () => { $("modalMask").hidden = true; });
  $("modalMask").addEventListener("click", (e) => {
    if (e.target === $("modalMask")) $("modalMask").hidden = true;
  });

  loadDims().then(loadRecent);
}

init();
