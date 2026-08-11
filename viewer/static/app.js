const API = "";
let frames = [], feed = [], states = [], runId = null, idx = 0, timer = null, liveWs = null;
let isolated = null; // null = show every kind; otherwise show only this one
let selectedAnomaly = null; // feed index of the anomaly HEAL should address

function kindForEvent(et) {
  if (et === "milestone" || et === "map_change") return "milestone";
  if (
    et === "battle" || et === "overworld" ||
    et === "battle_end" || et === "battle_outcome" || et === "move_result"
  ) return "telemetry";
  if (et === "discovery") return "observation";
  if (et === "decision") return "decision";
  if (et === "stuck") return "anomaly";  // wedged off-plan — mirror feed.py
  return null;
}

function textForEvent(msg) {
  const et = msg.event_type;
  const data = msg.data || {};
  if (et === "milestone") return data.description || "milestone";
  if (et === "map_change") return `Map ${data.prev_map} → ${data.new_map}`;
  if (et === "battle") return `Battle — player HP ${data.player_hp}, enemy HP ${data.enemy_hp}`;
  if (et === "overworld") {
    const pos = data.position || {};
    return `map ${data.map_id} (${pos.x},${pos.y}) ${data.action || ""}`.trim();
  }
  if (et === "stuck") return `Stuck \xd7${data.streak} at ${JSON.stringify(data.position || {})}`;
  if (et === "discovery") return data.text || "discovery";
  if (et === "battle_end") {
    const outcome = data.won ? "won" : "lost";
    return `Battle ${outcome} vs ${data.opponent_species} (Lv${data.opponent_level})`;
  }
  if (et === "battle_outcome") {
    const outcome = data.won ? "won" : "lost";
    return `Battle outcome: ${outcome} vs ${data.enemy_species} (Lv${data.enemy_level})`;
  }
  if (et === "move_result") {
    const result = data.fainted ? "enemy fainted" : `${data.damage_dealt} dmg`;
    return `${data.user_species} used ${data.move} — ${result}`;
  }
  if (et === "decision") {
    const buttons = (data.buttons || []).join("+") || "wait";
    return `▸ ${buttons} — ${data.reason || ""}`;
  }
  return et || "event";
}

function beatNumberFromLabel(label) {
  const m = /^(\d+)\s*·/.exec(label || "");
  return m ? m[1] : null;
}

function maybePushBeatRoute(label) {
  // A /run/<id> deep link is already unambiguous — never downgrade it to a beat
  // number, which several runs share.
  if (location.pathname.startsWith("/run/")) return;
  const beat = beatNumberFromLabel(label);
  if (beat && location.pathname !== `/${beat}`) {
    history.pushState({}, "", `/${beat}`);
  }
}

function closeLive() {
  if (liveWs) { liveWs.close(); liveWs = null; }
}

async function showGrid() {
  stop();
  closeLive();
  if (location.pathname !== "/") history.pushState({}, "", "/");
  const { runs } = await (await fetch(`${API}/api/runs`)).json();
  const g = document.getElementById("grid");
  g.innerHTML = "";
  runs.forEach(r => {
    const tile = document.createElement("div");
    tile.className = `tile ${r.status}`;
    const thumbnailHtml = r.thumbnail
      ? `<img src="${API}/runs/${r.run_id}/frames/${r.thumbnail}">`
      : `<div class="tile-noframe">no preview</div>`;
    const labelHtml = r.label ? `<b class="run-label">${r.label}</b><br>` : "";
    tile.innerHTML = `${thumbnailHtml}
      <div class="meta">${labelHtml}${r.run_id}<br>⚔️${r.battles_won} 🗺️${r.maps_visited}</div>`;
    tile.addEventListener("click", () => { document.body.dataset.view = "focus"; selectRun(r.run_id, r.label); });
    g.appendChild(tile);
  });
  document.body.dataset.view = "grid";
}

async function routeInitial() {
  const byId = /^\/run\/([\w-]+)$/.exec(location.pathname);
  const byBeat = /^\/(\d+)$/.exec(location.pathname);
  if (!byId && !byBeat) { showGrid(); return; }
  const { runs } = await (await fetch(`${API}/api/runs`)).json();
  // Beat numbers are ambiguous — several runs share a "7 ·" label and the first
  // match wins — so a run_id link is the one that survives a demo.
  const match = byId
    ? runs.find(r => r.run_id === byId[1])
    : runs.find(r => beatNumberFromLabel(r.label) === byBeat[1]);
  if (!match) { showGrid(); return; }
  document.body.dataset.view = "focus";
  await selectRun(match.run_id, match.label);
}

async function selectRun(id, label) {
  runId = id;
  closeLive();
  resetHealUI();
  maybePushBeatRoute(label);
  const detail = await (await fetch(`${API}/api/runs/${id}`)).json();
  frames = detail.frames;
  feed = (await (await fetch(`${API}/api/runs/${id}/feed`)).json()).feed;
  states = (await (await fetch(`${API}/api/runs/${id}/agent_state`)).json()).states;
  idx = 0;
  renderFeed();
  showFrame(idx);
  renderStatePanel(frames.length ? turnForFrame(idx) : 0);
  if (detail.status === "live") {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    liveWs = new WebSocket(`${proto}//${location.host}/ws/live/${id}`);
    liveWs.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "done") {
        closeLive();
      } else if (msg.type === "anomaly") {
        // Same text shape as the server-side REST merge (feed.py build_feed).
        feed.push({
          kind: "anomaly",
          turn: msg.turn || 0,
          ts: "",
          text: `${msg.alert_type || "ANOMALY"}: ${msg.detail || ""}`,
        });
        renderFeed();
      } else if (msg.type === "event") {
        if (msg.event_type === "agent_state") {
          states.push({ turn: msg.turn, ts: msg.occurred_at || "", data: msg.data || {} });
          renderStatePanel(msg.turn);
          return;
        }
        const kind = kindForEvent(msg.event_type);
        if (kind !== null) {
          feed.push({ kind, turn: msg.turn, ts: msg.occurred_at || "", text: textForEvent(msg) });
          renderFeed();
        }
      } else if (msg.type === "frame") {
        document.getElementById("screen").src = `data:image/png;base64,${msg.png_b64}`;
      }
    };
  } else {
    play();
  }
}

function renderFeed() {
  const ul = document.getElementById("feed");
  ul.innerHTML = "";
  feed.forEach((e, i) => {
    if (isolated !== null && e.kind !== isolated) return;
    const li = document.createElement("li");
    li.className = `entry ${e.kind}`;
    if (i === selectedAnomaly) li.classList.add("selected");
    li.dataset.feedIdx = i;
    // ts is ISO-8601 ("2026-07-19T14:17:26.000000Z") — show the HH:MM:SS slice.
    const time = e.ts ? e.ts.slice(11, 19) : "";
    li.textContent = `T${e.turn}${time ? " " + time : ""} [${e.kind}] ${e.text}`;
    li.addEventListener("click", () => {
      stop();
      showFrame(frameIndexForTurn(e.turn));
      // Clicking an anomaly also arms HEAL to address it (click again to disarm).
      if (e.kind === "anomaly") {
        selectedAnomaly = selectedAnomaly === i ? null : i;
        renderFeed();
        updateHealTarget();
      }
    });
    ul.appendChild(li);
  });
  highlightCurrentFeedEntry();
}

function stateForTurn(turn) {
  let best = null;
  for (const s of states) {
    if (s.turn <= turn) best = s;
    else break;
  }
  return best;
}

function renderStatePanel(turn) {
  const snap = stateForTurn(turn);
  const policy = document.getElementById("st-policy");
  if (!snap) {
    policy.textContent = "no agent state";
    ["st-plan", "st-memory", "st-status"].forEach(id => { document.getElementById(id).textContent = ""; });
    updateStatsBar(turn, null);
    return;
  }
  const d = snap.data;
  policy.textContent = `tier: ${d.tier || "?"}`;
  const wps = (d.route_waypoints || []).map(w => `(${w.x},${w.y})`).join(" → ");
  document.getElementById("st-plan").textContent = `${d.goal || "no active goal"}${wps ? "\nroute: " + wps : ""}`;
  document.getElementById("st-memory").textContent = d.notes_excerpt || "(empty)";
  const pos = d.position || {};
  document.getElementById("st-status").textContent =
    `map ${pos.map_id} (${pos.x},${pos.y})\nparty: ${d.party_count}  stuck: ${d.stuck_streak}`;
  updateStatsBar(turn, d);
}

function updateStatsBar(turn, d) {
  document.getElementById("sb-run").textContent = runId || "";
  document.getElementById("sb-tier").textContent = d ? `tier ${d.tier}` : "";
  document.getElementById("sb-turn").textContent = `Turn ${turn}`;
  document.getElementById("sb-battles").textContent = d ? `⚔️ ${d.battles_won}` : "";
  document.getElementById("sb-maps").textContent = d ? `🗺️ ${d.maps_visited}` : "";
}

function turnForFrame(i) {
  return parseInt(frames[i] || "0", 10) || 0;
}

function frameIndexForTurn(turn) {
  for (let i = 0; i < frames.length; i++) {
    if (turnForFrame(i) >= turn) return i;
  }
  return frames.length - 1;
}

function currentFeedEntryIndex(frameTurn) {
  let best = -1;
  for (let i = 0; i < feed.length; i++) {
    if (feed[i].turn <= frameTurn) best = i;
    else break;
  }
  return best;
}

function highlightCurrentFeedEntry() {
  const ul = document.getElementById("feed");
  const currentIdx = currentFeedEntryIndex(turnForFrame(idx));
  ul.querySelectorAll("li.entry").forEach(li => li.classList.remove("current"));
  if (currentIdx < 0) return;
  const li = ul.querySelector(`li[data-feed-idx="${currentIdx}"]`);
  if (li) {
    li.classList.add("current");
    li.scrollIntoView({ block: "nearest" });
  }
}

function showFrame(i) {
  if (!frames.length) return;
  idx = Math.max(0, Math.min(i, frames.length - 1));
  document.getElementById("screen").src = `${API}/runs/${runId}/frames/${frames[idx]}`;
  document.getElementById("scrub").value = idx;
  document.getElementById("scrub").max = frames.length - 1;
  const readout = document.getElementById("turn-readout");
  if (readout) readout.textContent = `Turn ${turnForFrame(idx)}`;
  highlightCurrentFeedEntry();
  renderStatePanel(turnForFrame(idx));
}

// Playback speed (ms per frame). Higher = slower. Tune live with [ and ] keys.
let frameDelay = 650;
function currentFrameDelay() {
  const currentIdx = currentFeedEntryIndex(turnForFrame(idx));
  const kind = currentIdx >= 0 ? feed[currentIdx].kind : null;
  return kind === "telemetry" ? frameDelay * 2 : frameDelay;
}
function play() {
  stop();
  scheduleNext();
}
function scheduleNext() {
  timer = setTimeout(() => {
    showFrame(idx >= frames.length - 1 ? 0 : idx + 1);
    scheduleNext();
  }, currentFrameDelay());
}
function stop() { if (timer) clearTimeout(timer); timer = null; }
function setSpeed(ms) {
  frameDelay = Math.max(80, Math.min(2000, ms));
  if (timer) play();  // restart the loop at the new speed
}

// HEAL button: turn the armed anomaly into the prompt scripts/discovery.py would
// hand its proposer, for a human to paste into Claude Code. Parameter racing
// still happens — automatically, after every run — but a genome can't fix a
// capability gap, and that is what these wedges are.
function resetHealUI() {
  selectedAnomaly = null;
  closeComposer();
  updateHealTarget();
}

// Name the wedge honestly: a terminal-length streak is a different failure from
// ordinary thrash (mirrors healer.py TERMINAL_WEDGE_STREAK).
function ruleForAnomaly(entry) {
  const m = /Stuck ×(\d+)/.exec(entry?.text || "");
  return m && parseInt(m[1], 10) >= 50 ? "terminal-wedge" : "navigation-thrash";
}

// Prompts are only as good as the operator note, so seed the box with the shape
// of a useful one for the rule in question.
const NOTE_PLACEHOLDERS = {
  "terminal-wedge": "e.g. it pressed into the same wall for 95 turns and never re-planned a route",
  "navigation-thrash": "type waa + Tab, or describe what you saw",
};

// Type a trigger, press Tab, get the sentence — nobody wants to watch a live
// demo being typed out. Keep these describing observed behaviour, not guessed
// causes: the prompt already carries the counted evidence, and a confident
// wrong theory in the note is worse than a plain description of the symptom.
const NOTE_SNIPPETS = {
  waa:
    "it ping-pongs between two adjacent tiles for thousands of turns — it replans from scratch " +
    "every turn, so when the exit is not reachable over the tiles it has actually seen, the " +
    "fallback target flips depending on which of the two tiles it is standing on, and nothing " +
    "ever commits to a path",
  wall:
    "it presses the same blocked direction for hundreds of turns and never re-plans a route " +
    "around the obstacle",
  door:
    "it steps in and out of the same doorway instead of walking away and continuing along the route",
};

function expandSnippet(event) {
  if (event.key !== "Tab" || event.shiftKey) return;
  const field = event.target;
  const caret = field.selectionStart;
  const trigger = /([A-Za-z]+)$/.exec(field.value.slice(0, caret));
  // hasOwn, not plain lookup: "constructor"+Tab must not paste Object.prototype.
  const key = trigger && trigger[1].toLowerCase();
  const body = key && Object.hasOwn(NOTE_SNIPPETS, key) ? NOTE_SNIPPETS[key] : null;
  if (!body) return;  // no match — Tab keeps its normal meaning and moves focus
  event.preventDefault();
  const start = caret - trigger[1].length;
  field.value = field.value.slice(0, start) + body + field.value.slice(caret);
  field.selectionStart = field.selectionEnd = start + body.length;
}

function armedAnomaly() {
  return selectedAnomaly === null ? null : feed[selectedAnomaly];
}

// The button says what it needs. Pressing HEAL with nothing armed used to race
// the whole run and report "run healthy" — true, useless, and confusing on stage.
function updateHealTarget() {
  const btn = document.getElementById("heal-btn");
  const readout = document.getElementById("heal-readout");
  const entry = armedAnomaly();
  btn.disabled = entry === null;
  readout.textContent = entry
    ? `T${entry.turn} · ${entry.text} · ${ruleForAnomaly(entry)}`
    : "select an anomaly in the feed first";
}

function closeComposer() {
  const dlg = document.getElementById("composer");
  if (dlg.open) dlg.close();
}

function openComposer() {
  const entry = armedAnomaly();
  if (!entry) return;
  const rule = ruleForAnomaly(entry);
  document.getElementById("composer-target").textContent =
    `${runId} · T${entry.turn} · ${entry.text} · rule: ${rule}`;
  const note = document.getElementById("composer-note");
  note.value = "";
  note.placeholder = NOTE_PLACEHOLDERS[rule] || "describe what went wrong";
  document.getElementById("composer-hint").textContent =
    `shortcuts — type and press Tab: ${Object.keys(NOTE_SNIPPETS).join(", ")}`;
  document.getElementById("composer-escalation").hidden = true;
  document.getElementById("composer-out").hidden = true;
  document.getElementById("composer-copy").disabled = true;
  document.getElementById("composer-draft").disabled = false;
  document.getElementById("composer-status").textContent = "";
  document.getElementById("composer").showModal();
  note.focus();
}

async function draftPrompt() {
  const entry = armedAnomaly();
  if (!entry) return;
  const draftBtn = document.getElementById("composer-draft");
  const status = document.getElementById("composer-status");
  draftBtn.disabled = true;
  status.textContent = "drafting…";

  // Any failure must land in the status line with the button re-enabled — a
  // fetch that throws mid-demo would otherwise wedge the composer until a
  // page reload (openComposer doesn't reset the draft button).
  let data;
  try {
    const r = await fetch(`${API}/api/runs/${runId}/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rule: ruleForAnomaly(entry),
        note: document.getElementById("composer-note").value,
        anomaly: `T${entry.turn} ${entry.text}`,
      }),
    });
    data = await r.json().catch(() => ({}));
    // FastAPI errors arrive as {detail}, the drafter's own as {error} — neither
    // may fall through to the success path or Copy would offer "undefined".
    if (!r.ok || data.error) {
      status.textContent = data.error || data.detail || `draft failed (HTTP ${r.status})`;
      return;
    }
  } catch (err) {
    status.textContent = `draft failed — ${err.message || "is the viewer server up?"}`;
    return;
  } finally {
    draftBtn.disabled = false;
  }
  status.textContent = "";
  const out = document.getElementById("composer-out");
  out.textContent = data.prompt;
  out.hidden = false;
  document.getElementById("composer-copy").disabled = false;

  // The whole point of the demo: this run already tripped the automatic path.
  const esc = document.getElementById("composer-escalation");
  if (data.escalation) {
    const e = data.escalation;
    esc.textContent =
      `healer already escalated this run — ${e.rule} · ${e.reason} ` +
      `(${e.position} of ${e.pending} pending in the discovery queue)`;
    esc.hidden = false;
  } else {
    esc.hidden = true;
  }
}

async function copyPrompt() {
  const status = document.getElementById("composer-status");
  try {
    await navigator.clipboard.writeText(document.getElementById("composer-out").textContent);
    status.textContent = "copied — paste it into Claude Code";
  } catch {
    status.textContent = "copy blocked by the browser — select the text and copy manually";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("scrub").addEventListener("input", e => { stop(); showFrame(+e.target.value); });
  document.getElementById("heal-btn").addEventListener("click", openComposer);
  document.getElementById("composer-note").addEventListener("keydown", expandSnippet);
  document.getElementById("composer-draft").addEventListener("click", draftPrompt);
  document.getElementById("composer-copy").addEventListener("click", copyPrompt);
  document.getElementById("composer-close").addEventListener("click", closeComposer);
  updateHealTarget();
  // Live playback controls: [ slower, ] faster, space = play/pause. Skipped
  // while the composer is open so typing a note doesn't drive the emulator.
  document.addEventListener("keydown", e => {
    if (document.getElementById("composer").open) return;
    if (e.key === "[") setSpeed(frameDelay + 150);
    else if (e.key === "]") setSpeed(frameDelay - 150);
    else if (e.key === " ") { e.preventDefault(); timer ? stop() : play(); }
  });
  document.querySelectorAll(".chip").forEach(c =>
    c.addEventListener("click", () => {
      isolated = isolated === c.dataset.kind ? null : c.dataset.kind;
      document.querySelectorAll(".chip").forEach(other =>
        other.classList.toggle("off", isolated !== null && other.dataset.kind !== isolated));
      renderFeed();
    }));
  window.addEventListener("popstate", routeInitial);
  routeInitial();
});
