/* 骰子酒馆 · 前端（纯手写，没依赖） */
const $ = (s) => document.querySelector(s);
const PIPS = {1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8]};

const G = {id: null, state: null, sel: new Set(), busy: false, prev: "", bustKey: ""};

/* ------------------------------------------------------------------ 小工具 */
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

async function api(path, payload) {
  const opt = payload === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  };
  try {
    const r = await fetch(path, opt);
    const d = await r.json();
    if (!r.ok && !d.error) d.error = "HTTP " + r.status;
    return d;
  } catch (e) {
    return {error: "连不上服务（server.py 还在跑吗？）"};
  }
}

function dieEl(v, cls) {
  const d = document.createElement("div");
  d.className = "die " + (cls || "");
  const on = PIPS[v] || [];
  for (let i = 0; i < 9; i++) {
    const p = document.createElement("span");
    p.className = "pip" + (on.includes(i) ? " on" : "");
    d.appendChild(p);
  }
  return d;
}

const isBotTurn = (st) => st && st.phase !== "over" && st.players[st.turn] && st.players[st.turn].bot;
const mySeat = (st) => (st ? Math.max(0, st.players.findIndex((p) => !p.bot)) : 0);
const myTurn = (st) => st && st.phase !== "over" && st.turn === mySeat(st);

/* ------------------------------------------------------------------ 渲染 */
function render(st, opts) {
  const o = opts || {};
  G.state = st;
  const over = st.phase === "over";

  /* 玩家卡 */
  const box = $("#players");
  box.innerHTML = "";
  st.players.forEach((p, i) => {
    const card = document.createElement("div");
    card.className = "pcard" + (i === st.turn && !over ? " active" : "");
    const pct = Math.min(100, Math.round((p.total / st.target) * 100));
    card.innerHTML = `
      <div class="avatar">${p.bot ? "🐟" : "🧍"}</div>
      <div class="who">
        <div class="name">${esc(p.name)}</div>
        <div class="role">${p.bot ? "这条鱼 · 手气" + ({easy: "心软", normal: "正常", bold: "心狠"}[G.style] || "") : "你"}</div>
      </div>
      <div class="score">${p.total}<small>分</small></div>
      <div class="bar"><i style="width:${pct}%"></i></div>`;
    box.appendChild(card);
  });

  /* 回合提示 */
  const bar = $("#turnbar");
  const whoTag = $("#whoTag");
  if (whoTag) {
    const w = st.who || {};
    whoTag.className = "whoTag " + (w.who || "stranger");
    whoTag.textContent = w.who === "owner" ? "对面：爸爸 · 她认出你了，会撒娇" : "对面：陌生的酒客 · 她会客气点";
  }
  const bust = st.phase === "bust" ? (st.busted || {}) : null;
  if (bust) markBust(st);
  if (over) bar.innerHTML = "牌局结束";
  else if (bust) {
    bar.innerHTML = `💥 <b>${esc(bust.who || "")}</b> 掷出 ${(bust.dice || []).join(" ")} —— 一颗都不计分` +
      (bust.lost ? `，<b>${bust.lost}</b> 分飞了` : "（这回合还没攒分）");
  } else if (isBotTurn(st)) bar.innerHTML = `<b>${esc(st.players[st.turn].name)}</b> 正在掷…`;
  else if (myTurn(st)) {
    bar.innerHTML = st.phase === "roll"
      ? "轮到 <b>你</b> · 掷骰子"
      : `本回合 <b>${st.turn_score}</b> 分 · 留骰继续，或者收下`;
  } else bar.textContent = "等她掷完";

  /* 骰子盘 */
  const stage = $("#stage");
  stage.innerHTML = "";
  stage.classList.toggle("bust", !!bust);
  const mine = myTurn(st);
  if (!st.rolled.length) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = over ? "牌局已结束"
      : st.phase === "roll" ? (mine ? "点下面的「掷骰」开扔" : "…")
      : "六颗全留下了，洗手重掷";
    stage.appendChild(e);
  } else {
    st.rolled.forEach((v, i) => {
      const d = dieEl(v, (bust ? "busted " : "") +
        (st.phase === "decide" && mine ? "clickable " : "") + (G.sel.has(i) ? "sel" : ""));
      if (o.animate) {
        d.classList.add("rolling");
        d.style.animationDelay = i * 70 + "ms";
      }
      if (st.phase === "decide" && mine) {
        d.onclick = () => {
          G.sel.has(i) ? G.sel.delete(i) : G.sel.add(i);
          render(G.state);
        };
      }
      stage.appendChild(d);
    });
  }

  /* 推荐组合 */
  const chips = $("#chips");
  chips.innerHTML = "";
  if (st.phase === "decide" && mine) {
    const opts2 = (st.legal || []).slice()
      .sort((a, b) => b.score - a.score || b.indices.length - a.indices.length)
      .slice(0, 4);
    opts2.forEach((op) => {
      const b = document.createElement("button");
      b.className = "chip";
      b.innerHTML = `${esc(op.label.replace(" = ", "="))} · <b>+${op.score}</b>`;
      b.onclick = () => act("keep", {indices: op.indices});
      chips.appendChild(b);
    });
  }

  /* 已留 */
  const held = $("#held");
  held.innerHTML = "";
  st.held.forEach((v) => held.appendChild(dieEl(v, "small")));
  if (!st.held.length) {
    const s = document.createElement("span");
    s.className = "lbl";
    s.textContent = "—";
    held.appendChild(s);
  }

  /* 按钮 */
  const roll = document.querySelector('[data-op="roll"]');
  const keep = document.querySelector('[data-op="keep"]');
  const bank = document.querySelector('[data-op="bank"]');
  roll.disabled = !(mine && st.phase === "roll");
  keep.disabled = !(mine && st.phase === "decide" && G.sel.size > 0);
  bank.disabled = !(mine && st.turn_score > 0);   // 掷完就能收，不必等桌面有骰子
  $("#hint").textContent = bust
    ? "手滑了……缓一下再接着掷"
    : st.phase === "decide" && mine
      ? "点桌上的骰子挑要留的，或者直接点上面推荐的组合"
      : over ? "" : st.phase === "decide" ? "等她决定" : "";

  /* 流水 */
  const log = $("#log");
  log.innerHTML = "";
  (st.log || []).slice().reverse().forEach((line) => {
    const li = document.createElement("li");
    li.innerHTML = colorize(line);
    log.appendChild(li);
  });

  /* 结算 */
  const ov = $("#overlay");
  if (over) {
    const w = st.players[st.winner] || {};
    $("#overTitle").textContent = w.bot ? "🐟 她赢了" : "🏆 你赢了";
    $("#overSub").textContent = `${w.name || ""} 先到 ${st.target} 分`;
    ov.classList.remove("hidden");
  } else ov.classList.add("hidden");
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}
function colorize(s) {
  return esc(s).replace(/([0-9]+)\s*分/g, "<b>$1 分</b>");
}

/* ------------------------------------------------------------------ 动作 */
async function newGame() {
  G.style = $("#style").value;
  G.brain = $("#brain").value;
  const d = await api("/api/new", {
    name: "你",
    target: parseInt($("#target").value, 10),
    style: G.style,
    brain: G.brain,
  });
  if (d.error) return toast(d.error);
  G.id = d.id;
  G.sel.clear();
  render(d.state);
  afterTurn(true);
}

async function act(op, extra) {
  if (G.busy || !G.id) return;
  G.busy = true;
  const payload = Object.assign({id: G.id, seat: G.state.turn, op: op}, extra || {});
  const d = await api("/api/action", payload);
  G.busy = false;
  if (d.error) {
    toast(d.error);
    if (d.state) render(d.state);
    return;
  }
  G.sel.clear();
  render(d.state, {animate: op === "roll"});
  if (d.state.phase === "bust") {          // 先把不点数的骰子亮一会儿，再收场换人
    setTimeout(settleBust, 2150);
    return;
  }
  afterTurn(false);
}

function settleBust() {
  if (!G.id || G.busy) return;
  if (!G.state || G.state.phase !== "bust") return;
  G.busy = true;
  const seat = G.state.turn;
  api("/api/action", {id: G.id, seat: seat, op: "settle"}).then((d) => {
    G.busy = false;
    if (d.error) return toast(d.error);
    G.sel.clear();
    render(d.state);
    afterTurn(false);
  });
}

function afterTurn(justStarted) {
  const st = G.state;
  if (!st || st.phase === "over" || !isBotTurn(st)) return;
  if (G.busy) return;
  setTimeout(runBot, justStarted ? 500 : 700);
}

async function runBot() {
  if (G.busy || !G.id) return;
  if (!isBotTurn(G.state)) return;
  G.busy = true;
  if (G.brain === "model" && $("#turnbar")) $("#turnbar").textContent = "她在盘算……（真模型，稍等）";
  const d = await api("/api/bot_turn", {id: G.id});
  if (d.error) {
    G.busy = false;
    return toast(d.error);
  }
  for (const step of d.steps || []) {
    if (step.line) toast(step.line);
    if (step.state) render(step.state, {animate: step.kind === "roll"});
    await sleep(step.kind === "bust" ? 1650 : 620);   // 爆骰那一帧多停一会儿（配合慢镜头）
  }
  G.busy = false;
  render(d.state);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ 动静 */
let AC = null;
function audioCtx() {
  if (!AC) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    AC = new C();
  }
  if (AC.state === "suspended") AC.resume();
  return AC;
}
// 浏览器不给无声页放声音：第一次碰页面时把音频解锁
["pointerdown", "keydown"].forEach((ev) =>
  window.addEventListener(ev, () => { audioCtx(); }, { once: true }));

/* 爆骰的那一声闷"咚"：低频下坠 + 一点碎响，纯 WebAudio，不依赖素材 */
function thud() {
  let ac;
  try { ac = audioCtx(); } catch (e) { return; }
  if (!ac) return;
  const t = ac.currentTime + 0.01;
  try {
    const o = ac.createOscillator(), g = ac.createGain(), f = ac.createBiquadFilter();
    o.type = "sine";
    o.frequency.setValueAtTime(125, t);
    o.frequency.exponentialRampToValueAtTime(42, t + 0.38);
    f.type = "lowpass"; f.frequency.setValueAtTime(340, t); f.frequency.exponentialRampToValueAtTime(160, t + 0.3);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.55, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.62);
    o.connect(f); f.connect(g); g.connect(ac.destination);
    o.start(t); o.stop(t + 0.65);

    const len = Math.floor(ac.sampleRate * 0.14);
    const buf = ac.createBuffer(1, len, ac.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const n = ac.createBufferSource(); n.buffer = buf;
    const nf = ac.createBiquadFilter(); nf.type = "bandpass"; nf.frequency.value = 1600; nf.Q.value = 0.8;
    const ng = ac.createGain(); ng.gain.value = 0.22;
    n.connect(nf); nf.connect(ng); ng.connect(ac.destination);
    n.start(t + 0.02);
  } catch (e) { /* 不给放就算了，画面照旧 */ }
}

/* 爆骰只响一次：同一个爆骰帧不重复触发 */
function markBust(st) {
  const key = st.phase === "bust" && st.busted
    ? [st.turn, (st.busted.dice || []).join(""), st.busted.lost].join("|") : "";
  if (key && key !== G.bustKey) { G.bustKey = key; thud(); }
  if (!key) G.bustKey = "";
}

/* ------------------------------------------------------------------ QQ 面板 */
async function pollQQ() {
  const d = await api("/api/qq/tables");
  const box = $("#qq");
  if (!d || d.error || !d.tables || !d.tables.length) {
    box.innerHTML = "QQ 群里没人开桌";
    return;
  }
  box.innerHTML = d.tables.map((t) =>
    `QQ 桌 <b>${esc(t.label)}</b>：${t.players.map((p) => `${esc(p.name)} ${p.total}`).join(" · ")}`
  ).join("<br>");
}

/* ------------------------------------------------------------------ 事件 */
document.querySelectorAll("[data-op]").forEach((b) => {
  b.onclick = () => {
    const op = b.dataset.op;
    if (op === "keep") {
      if (!G.sel.size) return toast("先点几颗骰子");
      act("keep", {indices: [...G.sel]});
    } else act(op);
  };
});
$("#newGame").onclick = newGame;
$("#again").onclick = () => { $("#overlay").classList.add("hidden"); newGame(); };
$("#sayBtn").onclick = async () => {
  if (!G.state) return toast("先开一局");
  const d = await api("/api/say", {state: G.state, event: myTurn(G.state) ? "taunt" : "keep"});
  toast("🐟 " + (d.text || "……"));
};
document.addEventListener("keydown", (e) => {
  if (!G.state || G.busy) return;
  if (e.key === " " || e.key === "Enter") {
    e.preventDefault();
    if (myTurn(G.state) && G.state.phase === "roll") act("roll");
    else if (myTurn(G.state) && G.sel.size) act("keep", {indices: [...G.sel]});
  }
});

G.style = $("#style").value;
pollQQ();
setInterval(pollQQ, 10000);
$("#stage").innerHTML = '<div class="empty">点右上角「开一局」</div>';
if (new URLSearchParams(location.search).has("auto")) newGame();
const demo = new URLSearchParams(location.search).get("demo");   // 调试用：自动走两步
if (demo === "bust") {                    // 调试用：只画一帧"爆骰"的样子
  render({
    target: 4000, phase: "bust", turn: 0, turn_score: 0, held: [1], rolled: [6, 6, 4], rolls: 2,
    players: [{name: "你", bot: false, uid: "me", total: 350},
              {name: "哦鲸鲸", bot: true, uid: "", total: 1200}],
    winner: null, busted: {dice: [6, 6, 4], lost: 400, who: "你", seat: 0}, legal: [],
    log: ["你 掷出 6 6 4 —— 一颗都留不出，爆了，400 分飞了"], last: {type: "bust"},
  });
} else if (demo) {
  newGame().then(async () => {
    await sleep(300);
    await act("roll");
    await sleep(700);
    if (demo === "2" && G.state.phase === "decide" && (G.state.legal || []).length) {
      await act("keep", {indices: G.state.legal[0].indices});
    }
  });
}
