"""Generate a dependency-free, self-contained HTML animation for a simulation.

The generated document embeds both the scenario and the serialized simulation
result.  It therefore works when opened directly from disk and does not require a
web server, JavaScript package, font, image, or network connection.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any, Dict, Mapping, Union


if TYPE_CHECKING:
    from smartclean_sim.simulation import SimulationResult


PathValue = Union[str, Path]


def _json_compatible(value: Any) -> Any:
    """Return a deterministic JSON-compatible copy of common config values."""

    if isinstance(value, Mapping):
        return {
            str(key): _json_compatible(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        "animation payload contains a non-JSON value: {}".format(
            type(value).__name__
        )
    )


def _safe_embedded_json(payload: Mapping[str, Any]) -> str:
    """Serialize JSON without allowing user data to terminate the script node."""

    serialized = json.dumps(
        _json_compatible(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    # HTML parsers recognize </script> even inside application/json.  Escaping the
    # opening angle bracket prevents that token while JSON.parse restores the exact
    # original value.  The other escapes also keep embedded data inert in HTML.
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


_DOCUMENT = Template(
    r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>$document_title</title>
  <style>
    :root {
      color-scheme: dark;
      --page: #071018;
      --panel: #101d28;
      --panel-soft: #152634;
      --line: #284154;
      --text: #ecf7ff;
      --muted: #9eb2c1;
      --accent: #50e3a4;
      --accent-strong: #20bb7c;
      --danger: #ff6b6b;
      --water: #37a9d6;
      --obstacle: #334a5c;
      --route: #f7c85d;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 12% 5%, #183245 0, transparent 34rem),
        var(--page);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .app {
      width: min(1180px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }

    h1 {
      margin: 0;
      font-size: clamp(1.35rem, 3vw, 2.15rem);
      letter-spacing: .015em;
    }

    .subtitle {
      margin: 7px 0 0;
      color: var(--muted);
      font-size: .93rem;
    }

    .status-pill {
      flex: 0 0 auto;
      border: 1px solid color-mix(in srgb, var(--accent) 52%, transparent);
      border-radius: 999px;
      padding: 7px 12px;
      background: color-mix(in srgb, var(--accent) 12%, transparent);
      color: var(--accent);
      font-size: .82rem;
      font-weight: 700;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 290px;
      gap: 16px;
      align-items: start;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: color-mix(in srgb, var(--panel) 94%, transparent);
      box-shadow: 0 18px 54px rgba(0, 0, 0, .24);
    }

    .canvas-panel { padding: 14px; }

    .canvas-shell {
      overflow: hidden;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: #0a151e;
    }

    canvas {
      display: block;
      width: 100%;
      min-height: 220px;
      touch-action: none;
    }

    .controls {
      display: grid;
      grid-template-columns: auto auto auto auto minmax(110px, 1fr) auto;
      gap: 8px;
      align-items: center;
      margin-top: 13px;
    }

    button, select {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--text);
      font: inherit;
    }

    button {
      min-width: 42px;
      padding: 7px 11px;
      cursor: pointer;
    }

    button:hover:not(:disabled), button:focus-visible, select:focus-visible {
      border-color: var(--accent);
      outline: none;
    }

    button:disabled { cursor: default; opacity: .38; }

    #playButton {
      border-color: var(--accent-strong);
      background: var(--accent-strong);
      color: #04150e;
      font-weight: 800;
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }

    select { padding: 6px 8px; }

    .frame-info {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 11px;
      color: var(--muted);
      font-size: .82rem;
    }

    .event-box {
      min-height: 43px;
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 9px;
      background: #0b1822;
      color: #c7d9e5;
      font-size: .86rem;
      line-height: 1.45;
    }

    aside { padding: 15px; }

    aside h2 {
      margin: 0 0 11px;
      font-size: .95rem;
      letter-spacing: .04em;
      color: var(--muted);
      text-transform: uppercase;
    }

    .metrics {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }

    .metric {
      min-height: 72px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #0c1923;
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: .73rem;
    }

    .metric strong {
      display: block;
      margin-top: 6px;
      overflow-wrap: anywhere;
      font-size: 1rem;
    }

    .legend {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 9px 12px;
      margin-top: 9px;
      color: #c3d3de;
      font-size: .8rem;
    }

    .legend div { display: flex; align-items: center; gap: 7px; }

    .swatch {
      width: 13px;
      height: 13px;
      flex: 0 0 auto;
      border: 2px solid transparent;
      border-radius: 3px;
      background: var(--obstacle);
    }

    .swatch.water { background: color-mix(in srgb, var(--water) 70%, #071018); }
    .swatch.route { height: 4px; border: 0; border-radius: 5px; background: var(--route); }
    .swatch.trash { border-radius: 50%; background: #f39b4a; }
    .swatch.dock { border-color: #7da9ff; background: transparent; transform: rotate(45deg); }
    .swatch.dynamic { border-radius: 50%; background: var(--danger); }
    .swatch.robot { border-radius: 50%; background: var(--accent); }

    .shortcut {
      margin: 17px 0 0;
      color: var(--muted);
      font-size: .76rem;
      line-height: 1.55;
    }

    @media (max-width: 820px) {
      .layout { grid-template-columns: 1fr; }
      .controls { grid-template-columns: auto auto auto auto 1fr; }
      .controls select { grid-column: 1 / -1; width: 100%; }
    }

    @media (max-width: 520px) {
      .app { width: min(100% - 16px, 1180px); padding-top: 16px; }
      header { align-items: flex-start; flex-direction: column; }
      .controls { grid-template-columns: repeat(4, 1fr); }
      .controls input { grid-column: 1 / -1; grid-row: 2; }
      .frame-info { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="app">
    <header>
      <div>
        <h1>$document_title</h1>
        <p class="subtitle">离线二维清扫过程回放 · 栅格坐标原点位于左上角</p>
      </div>
      <div class="status-pill" id="statePill">准备中</div>
    </header>

    <div class="layout">
      <section class="panel canvas-panel" aria-label="仿真动画">
        <div class="canvas-shell">
          <canvas id="worldCanvas" role="img" aria-label="清扫机器人栅格动画"></canvas>
        </div>

        <div class="controls" aria-label="回放控制">
          <button id="resetButton" type="button" title="回到第一帧">重置</button>
          <button id="previousButton" type="button" title="上一帧">后退</button>
          <button id="playButton" type="button" aria-pressed="false">播放</button>
          <button id="nextButton" type="button" title="下一帧">前进</button>
          <input id="timeline" type="range" min="0" max="0" value="0" step="1" aria-label="动画时间轴">
          <select id="speedSelect" aria-label="播放速度">
            <option value="0.5">0.5×</option>
            <option value="1" selected>1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
          </select>
        </div>

        <div class="frame-info">
          <span id="frameLabel">帧 0 / 0</span>
          <span id="stepLabel">仿真步 0</span>
          <span id="actionLabel">动作 —</span>
        </div>
        <div class="event-box" id="eventText" aria-live="polite">等待轨迹数据</div>
      </section>

      <aside class="panel">
        <h2>运行状态</h2>
        <div class="metrics">
          <div class="metric"><span>当前阶段</span><strong id="stateMetric">—</strong></div>
          <div class="metric"><span>清扫进度</span><strong id="cleanedMetric">0 / 0</strong></div>
          <div class="metric"><span>路径长度</span><strong id="pathMetric">0 格</strong></div>
          <div class="metric"><span>重规划</span><strong id="replanMetric">0 次</strong></div>
          <div class="metric"><span>碰撞</span><strong id="collisionMetric">0 次</strong></div>
          <div class="metric"><span>最终结果</span><strong id="resultMetric">—</strong></div>
        </div>

        <h2 style="margin-top: 20px">图例</h2>
        <div class="legend">
          <div><i class="swatch"></i>静态障碍</div>
          <div><i class="swatch water"></i>危险区域</div>
          <div><i class="swatch route"></i>已行轨迹</div>
          <div><i class="swatch trash"></i>待清垃圾</div>
          <div><i class="swatch dock"></i>充电点</div>
          <div><i class="swatch dynamic"></i>动态障碍</div>
          <div><i class="swatch robot"></i>清扫机器人</div>
        </div>
        <p class="shortcut">快捷键：空格播放或暂停，左右方向键逐帧查看。所有场景和轨迹数据均已嵌入本文件。</p>
      </aside>
    </div>
  </main>

  <script id="simulation-data" type="application/json">$embedded_payload</script>
  <script>
  "use strict";

  (function () {
    const payloadNode = document.getElementById("simulation-data");
    const payload = JSON.parse(payloadNode.textContent);
    const scenario = payload.scenario || {};
    const result = payload.result || {};
    const trace = result.trace || {};
    const rawFrames = Array.isArray(trace.frames) ? trace.frames : [];
    const initialTrash = Array.isArray(scenario.trash) ? scenario.trash : [];

    function itemId(item) {
      if (!item || typeof item !== "object") return "";
      return String(item.id !== undefined ? item.id : (item.item_id || ""));
    }

    function asPosition(value) {
      if (Array.isArray(value) && value.length >= 2) {
        return {x: Number(value[0]), y: Number(value[1])};
      }
      if (value && typeof value === "object" && value.x !== undefined && value.y !== undefined) {
        return {x: Number(value.x), y: Number(value.y)};
      }
      return null;
    }

    const defaultPosition = asPosition(result.final_position) || asPosition(scenario.start) || {x: 0, y: 0};
    const fallbackFrame = {
      frame_index: 0,
      sim_step: 0,
      state: result.status || "NO_TRACE",
      action: "terminal",
      robot_position: [defaultPosition.x, defaultPosition.y],
      dynamic_obstacles: [],
      remaining_trash_ids: initialTrash.map(itemId),
      cleaned_ids: Array.isArray(result.cleaned_ids) ? result.cleaned_ids : [],
      cleaned_this_frame: [],
      events: ["未提供逐帧轨迹"]
    };
    const frames = rawFrames.length ? rawFrames : [fallbackFrame];

    const canvas = document.getElementById("worldCanvas");
    const context = canvas.getContext("2d");
    const resetButton = document.getElementById("resetButton");
    const previousButton = document.getElementById("previousButton");
    const playButton = document.getElementById("playButton");
    const nextButton = document.getElementById("nextButton");
    const timeline = document.getElementById("timeline");
    const speedSelect = document.getElementById("speedSelect");
    const statePill = document.getElementById("statePill");
    const stateMetric = document.getElementById("stateMetric");
    const cleanedMetric = document.getElementById("cleanedMetric");
    const pathMetric = document.getElementById("pathMetric");
    const replanMetric = document.getElementById("replanMetric");
    const collisionMetric = document.getElementById("collisionMetric");
    const resultMetric = document.getElementById("resultMetric");
    const frameLabel = document.getElementById("frameLabel");
    const stepLabel = document.getElementById("stepLabel");
    const actionLabel = document.getElementById("actionLabel");
    const eventText = document.getElementById("eventText");

    const worldWidth = Math.max(1, Number(scenario.width) || 1);
    const worldHeight = Math.max(1, Number(scenario.height) || 1);
    let viewWidth = 800;
    let viewHeight = 500;
    let currentIndex = 0;
    let timer = null;
    let playing = false;
    const baseFrameDuration = 620;

    timeline.max = String(Math.max(0, frames.length - 1));

    function metricNumber(name) {
      const metrics = result.metrics || {};
      const number = Number(metrics[name]);
      return Number.isFinite(number) ? number : 0;
    }

    function cellGeometry() {
      return {width: viewWidth / worldWidth, height: viewHeight / worldHeight};
    }

    function cellCenter(position) {
      const cell = cellGeometry();
      return {
        x: (position.x + 0.5) * cell.width,
        y: (position.y + 0.5) * cell.height
      };
    }

    function fillCell(position, color, inset) {
      const cell = cellGeometry();
      const gap = inset || 0;
      context.fillStyle = color;
      context.fillRect(
        position.x * cell.width + gap,
        position.y * cell.height + gap,
        Math.max(0, cell.width - gap * 2),
        Math.max(0, cell.height - gap * 2)
      );
    }

    function drawGround() {
      context.fillStyle = "#0a151e";
      context.fillRect(0, 0, viewWidth, viewHeight);
      const cell = cellGeometry();
      context.strokeStyle = "rgba(117, 151, 174, 0.16)";
      context.lineWidth = 1;
      context.beginPath();
      for (let x = 0; x <= worldWidth; x += 1) {
        context.moveTo(x * cell.width, 0);
        context.lineTo(x * cell.width, viewHeight);
      }
      for (let y = 0; y <= worldHeight; y += 1) {
        context.moveTo(0, y * cell.height);
        context.lineTo(viewWidth, y * cell.height);
      }
      context.stroke();
    }

    function hazardRows() {
      const hazards = scenario.hazards;
      const rows = [];
      if (Array.isArray(hazards)) {
        hazards.forEach(function (entry) {
          if (!entry || typeof entry !== "object") return;
          const kind = String(entry.kind || entry.type || "hazard");
          const values = Array.isArray(entry.positions) ? entry.positions : [entry.position];
          values.forEach(function (value) {
            const position = asPosition(value);
            if (position) rows.push({kind: kind, position: position});
          });
        });
      } else if (hazards && typeof hazards === "object") {
        Object.keys(hazards).sort().forEach(function (kind) {
          const values = Array.isArray(hazards[kind]) ? hazards[kind] : [];
          values.forEach(function (value) {
            const position = asPosition(value);
            if (position) rows.push({kind: kind, position: position});
          });
        });
      }
      return rows;
    }

    function drawHazards() {
      hazardRows().forEach(function (hazard) {
        const color = hazard.kind === "water" ? "rgba(55, 169, 214, 0.46)" : "rgba(231, 166, 68, 0.42)";
        fillCell(hazard.position, color, 2);
      });
    }

    function drawStaticObstacles() {
      const obstacles = Array.isArray(scenario.static_obstacles) ? scenario.static_obstacles : [];
      obstacles.forEach(function (value) {
        const position = asPosition(value);
        if (!position) return;
        fillCell(position, "#334a5c", 1);
        const cell = cellGeometry();
        context.strokeStyle = "rgba(188, 211, 225, 0.18)";
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(position.x * cell.width + 4, position.y * cell.height + 4);
        context.lineTo((position.x + 1) * cell.width - 4, (position.y + 1) * cell.height - 4);
        context.stroke();
      });
    }

    function routePositions() {
      const positions = [];
      for (let index = 0; index <= currentIndex; index += 1) {
        const position = asPosition(frames[index].robot_position);
        if (!position) continue;
        const previous = positions.length ? positions[positions.length - 1] : null;
        if (!previous || previous.x !== position.x || previous.y !== position.y) {
          positions.push(position);
        }
      }
      return positions;
    }

    function drawRoute() {
      const positions = routePositions();
      if (positions.length < 2) return;
      const cell = cellGeometry();
      context.strokeStyle = "rgba(247, 200, 93, 0.88)";
      context.lineWidth = Math.max(2, Math.min(cell.width, cell.height) * 0.12);
      context.lineCap = "round";
      context.lineJoin = "round";
      context.beginPath();
      positions.forEach(function (position, index) {
        const center = cellCenter(position);
        if (index === 0) context.moveTo(center.x, center.y);
        else context.lineTo(center.x, center.y);
      });
      context.stroke();
    }

    function trashSymbol(kind) {
      const symbols = {
        fallen_leaves: "L",
        plastic_bottle: "B",
        paper_scrap: "P",
        paper_cup: "C",
        aluminum_can: "A"
      };
      return symbols[kind] || "T";
    }

    function drawTrash(frame) {
      const provided = Array.isArray(frame.remaining_trash_ids);
      const remaining = new Set(provided ? frame.remaining_trash_ids.map(String) : initialTrash.map(itemId));
      const cell = cellGeometry();
      initialTrash.forEach(function (item) {
        if (!remaining.has(itemId(item))) return;
        const position = asPosition(item.position);
        if (!position) return;
        const center = cellCenter(position);
        const radius = Math.max(5, Math.min(cell.width, cell.height) * 0.25);
        context.fillStyle = "#f39b4a";
        context.beginPath();
        context.arc(center.x, center.y, radius, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = "#291407";
        context.font = "700 " + Math.max(9, radius) + "px sans-serif";
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(trashSymbol(String(item.kind || item.type || "")), center.x, center.y + 0.5);
      });
    }

    function drawDock() {
      const position = asPosition(scenario.dock || scenario.start);
      if (!position) return;
      const center = cellCenter(position);
      const cell = cellGeometry();
      const radius = Math.max(5, Math.min(cell.width, cell.height) * 0.29);
      context.save();
      context.translate(center.x, center.y);
      context.rotate(Math.PI / 4);
      context.fillStyle = "rgba(64, 101, 166, 0.26)";
      context.strokeStyle = "#7da9ff";
      context.lineWidth = 2;
      context.fillRect(-radius, -radius, radius * 2, radius * 2);
      context.strokeRect(-radius, -radius, radius * 2, radius * 2);
      context.restore();
    }

    function drawDynamicObstacles(frame) {
      const obstacles = Array.isArray(frame.dynamic_obstacles) ? frame.dynamic_obstacles : [];
      const cell = cellGeometry();
      obstacles.forEach(function (obstacle) {
        const position = asPosition(obstacle && obstacle.position);
        if (!position) return;
        const center = cellCenter(position);
        const radius = Math.max(6, Math.min(cell.width, cell.height) * 0.26);
        context.fillStyle = "#ff6b6b";
        context.strokeStyle = "#511b25";
        context.lineWidth = 2;
        context.beginPath();
        context.arc(center.x, center.y, radius, 0, Math.PI * 2);
        context.fill();
        context.stroke();
        context.fillStyle = "#2a0810";
        context.font = "800 " + Math.max(9, radius) + "px sans-serif";
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText("!", center.x, center.y + 0.5);
      });
    }

    function previousDistinctRobotPosition() {
      const current = asPosition(frames[currentIndex].robot_position);
      if (!current) return null;
      for (let index = currentIndex - 1; index >= 0; index -= 1) {
        const candidate = asPosition(frames[index].robot_position);
        if (candidate && (candidate.x !== current.x || candidate.y !== current.y)) return candidate;
      }
      return null;
    }

    function drawRobot(frame) {
      const position = asPosition(frame.robot_position);
      if (!position) return;
      const center = cellCenter(position);
      const cell = cellGeometry();
      const radius = Math.max(7, Math.min(cell.width, cell.height) * 0.31);
      context.fillStyle = "#50e3a4";
      context.strokeStyle = "#063926";
      context.lineWidth = 3;
      context.beginPath();
      context.arc(center.x, center.y, radius, 0, Math.PI * 2);
      context.fill();
      context.stroke();

      const previous = previousDistinctRobotPosition();
      const angle = previous ? Math.atan2(position.y - previous.y, position.x - previous.x) : 0;
      context.strokeStyle = "#05281c";
      context.lineWidth = Math.max(2, radius * 0.2);
      context.lineCap = "round";
      context.beginPath();
      context.moveTo(center.x, center.y);
      context.lineTo(center.x + Math.cos(angle) * radius * 0.72, center.y + Math.sin(angle) * radius * 0.72);
      context.stroke();
    }

    function draw() {
      const frame = frames[currentIndex];
      context.clearRect(0, 0, viewWidth, viewHeight);
      drawGround();
      drawHazards();
      drawStaticObstacles();
      drawRoute();
      drawTrash(frame);
      drawDock();
      drawDynamicObstacles(frame);
      drawRobot(frame);
    }

    function updateLabels() {
      const frame = frames[currentIndex];
      const state = String(frame.state || "UNKNOWN");
      const action = String(frame.action || "—");
      const events = Array.isArray(frame.events) ? frame.events : [];
      const cleaned = Array.isArray(frame.cleaned_ids) ? frame.cleaned_ids.length : 0;
      const totalTargets = metricNumber("total_targets");

      statePill.textContent = state;
      stateMetric.textContent = state;
      cleanedMetric.textContent = String(cleaned) + " / " + String(totalTargets);
      pathMetric.textContent = String(metricNumber("path_length_cells")) + " 格";
      replanMetric.textContent = String(metricNumber("replans")) + " 次";
      collisionMetric.textContent = String(metricNumber("collisions")) + " 次";
      resultMetric.textContent = String(result.status || "—");
      frameLabel.textContent = "帧 " + String(currentIndex + 1) + " / " + String(frames.length);
      stepLabel.textContent = "仿真步 " + String(frame.sim_step !== undefined ? frame.sim_step : 0);
      actionLabel.textContent = "动作 " + action;
      eventText.textContent = events.length ? events.map(String).join(" · ") : "当前帧无新增事件";
      timeline.value = String(currentIndex);
      previousButton.disabled = currentIndex === 0;
      nextButton.disabled = currentIndex === frames.length - 1;
    }

    function render() {
      draw();
      updateLabels();
    }

    function stop() {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      playing = false;
      playButton.textContent = "播放";
      playButton.setAttribute("aria-pressed", "false");
    }

    function queueNext() {
      if (!playing) return;
      const speed = Math.max(0.1, Number(speedSelect.value) || 1);
      timer = window.setTimeout(function () {
        if (currentIndex >= frames.length - 1) {
          stop();
          return;
        }
        currentIndex += 1;
        render();
        queueNext();
      }, baseFrameDuration / speed);
    }

    function play() {
      if (playing) {
        stop();
        return;
      }
      if (currentIndex >= frames.length - 1) currentIndex = 0;
      playing = true;
      playButton.textContent = "暂停";
      playButton.setAttribute("aria-pressed", "true");
      render();
      queueNext();
    }

    function selectFrame(index) {
      stop();
      currentIndex = Math.max(0, Math.min(frames.length - 1, index));
      render();
    }

    function resizeCanvas() {
      const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
      viewWidth = Math.max(280, canvas.parentElement.clientWidth || 800);
      viewHeight = Math.max(220, viewWidth * worldHeight / worldWidth);
      canvas.style.height = String(viewHeight) + "px";
      canvas.width = Math.round(viewWidth * pixelRatio);
      canvas.height = Math.round(viewHeight * pixelRatio);
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      render();
    }

    resetButton.addEventListener("click", function () { selectFrame(0); });
    previousButton.addEventListener("click", function () { selectFrame(currentIndex - 1); });
    playButton.addEventListener("click", play);
    nextButton.addEventListener("click", function () { selectFrame(currentIndex + 1); });
    timeline.addEventListener("input", function () { selectFrame(Number(timeline.value)); });
    speedSelect.addEventListener("change", function () {
      if (!playing) return;
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      queueNext();
    });
    document.addEventListener("keydown", function (event) {
      const tagName = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : "";
      if (tagName === "input" || tagName === "select" || tagName === "button") return;
      if (event.code === "Space") {
        event.preventDefault();
        play();
      } else if (event.code === "ArrowLeft") {
        event.preventDefault();
        selectFrame(currentIndex - 1);
      } else if (event.code === "ArrowRight") {
        event.preventDefault();
        selectFrame(currentIndex + 1);
      }
    });
    window.addEventListener("resize", resizeCanvas);

    resizeCanvas();
  }());
  </script>
</body>
</html>
"""
)


def render_animation_html(
    scenario: Mapping[str, Any],
    result: "SimulationResult",
    title: str = "SmartClean-Sim",
) -> str:
    """Return a complete HTML/Canvas animation document.

    ``result.to_dict()`` is expected to expose its replay frames at
    ``trace.frames``.  A terminal fallback frame is still rendered when an older
    result without trace data is supplied, keeping the exporter fail-soft for
    previously saved results.
    """

    if not isinstance(scenario, Mapping):
        raise TypeError("scenario must be a mapping")
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    to_dict = getattr(result, "to_dict", None)
    if not callable(to_dict):
        raise TypeError("result must provide to_dict()")
    result_payload = to_dict()
    if not isinstance(result_payload, Mapping):
        raise TypeError("result.to_dict() must return a mapping")

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "scenario": scenario,
        "result": result_payload,
    }
    return _DOCUMENT.substitute(
        document_title=html.escape(title, quote=True),
        embedded_payload=_safe_embedded_json(payload),
    )


def write_animation_html(
    scenario: Mapping[str, Any],
    result: "SimulationResult",
    output_path: PathValue,
    title: str = "SmartClean-Sim",
) -> Path:
    """Write a self-contained animation as UTF-8 and return its path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_animation_html(scenario, result, title=title), encoding="utf-8")
    return path
