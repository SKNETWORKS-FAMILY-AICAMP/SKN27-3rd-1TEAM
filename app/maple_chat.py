import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="이상한 인내의 숲",
    page_icon="🌳",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        max-width: 1180px;
    }
    h1, h2, h3, p, li {
        letter-spacing: 0;
    }
    .game-note {
        border: 2px dashed #111;
        background: #fff;
        color: #111;
        padding: 12px 14px;
        font-family: "Comic Sans MS", "Malgun Gothic", sans-serif;
        box-shadow: 5px 5px 0 #ddd;
        margin-bottom: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("이상한 인내의 숲")
st.markdown(
    """
    <div class="game-note">
    마우스로 그림판에 그리다 만 것 같은 숲 점프맵입니다.
    방향키 또는 WASD로 이동하고, Space/W/↑ 로 점프합니다. 이상한 빨간 막대에 닿으면 체크포인트로 돌아갑니다.
    </div>
    """,
    unsafe_allow_html=True,
)

game_html = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    html, body {
      margin: 0;
      padding: 0;
      background: #ffffff;
      overflow: hidden;
      font-family: "Comic Sans MS", "Malgun Gothic", sans-serif;
    }
    .wrap {
      width: 100%;
      min-height: 720px;
      display: grid;
      place-items: center;
      background: #fff;
    }
    .frame {
      width: min(100%, 1060px);
      border: 3px solid #111;
      background: white;
      box-shadow: 8px 8px 0 #d6d6d6;
      position: relative;
    }
    canvas {
      width: 100%;
      height: auto;
      display: block;
      image-rendering: pixelated;
      background: white;
    }
    .hint {
      position: absolute;
      left: 10px;
      bottom: 8px;
      color: #111;
      background: rgba(255,255,255,.78);
      border: 2px dotted #333;
      padding: 4px 7px;
      font-size: 13px;
      user-select: none;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="frame">
      <canvas id="game" width="1060" height="620" tabindex="0" aria-label="낙서풍 점프 미니게임"></canvas>
      <div class="hint">Click game first · WASD/Arrow move · Space jump · R restart</div>
    </div>
  </div>
  <script>
    const canvas = document.getElementById("game");
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;

    const W = canvas.width;
    const H = canvas.height;
    const keys = new Set();
    const rand = (n) => Math.sin(n * 999.31) * 43758.5453 % 1;

    const spawn = { x: 42, y: 535 };
    const checkpoints = [
      { x: 42, y: 535, got: true },
      { x: 365, y: 402, got: false },
      { x: 675, y: 276, got: false },
      { x: 925, y: 142, got: false }
    ];
    let currentCheckpoint = checkpoints[0];

    const platforms = [
      { x: 20, y: 585, w: 180, h: 18, tilt: -1 },
      { x: 220, y: 548, w: 108, h: 14, tilt: 2 },
      { x: 365, y: 515, w: 86, h: 15, tilt: -2 },
      { x: 505, y: 475, w: 128, h: 16, tilt: 1 },
      { x: 680, y: 445, w: 94, h: 14, tilt: -1 },
      { x: 830, y: 405, w: 160, h: 16, tilt: 2 },
      { x: 580, y: 365, w: 106, h: 14, tilt: -2 },
      { x: 390, y: 420, w: 115, h: 16, tilt: 1 },
      { x: 225, y: 365, w: 100, h: 14, tilt: -1 },
      { x: 80, y: 305, w: 130, h: 16, tilt: 2 },
      { x: 265, y: 255, w: 92, h: 14, tilt: -1 },
      { x: 445, y: 215, w: 120, h: 15, tilt: 2 },
      { x: 635, y: 295, w: 115, h: 15, tilt: -2 },
      { x: 805, y: 245, w: 125, h: 16, tilt: 1 },
      { x: 930, y: 185, w: 108, h: 14, tilt: -1 },
      { x: 760, y: 135, w: 120, h: 15, tilt: 2 },
      { x: 555, y: 105, w: 105, h: 14, tilt: -2 },
      { x: 330, y: 130, w: 135, h: 16, tilt: 1 },
    ];

    const ropes = [
      { x: 178, y: 305, h: 280 },
      { x: 606, y: 215, h: 255 },
      { x: 960, y: 185, h: 220 },
    ];

    const hazards = [
      { x: 245, y: 524, w: 34, h: 18, axis: "x", range: 78, speed: 1.2, base: 245, phase: 0 },
      { x: 525, y: 448, w: 35, h: 18, axis: "x", range: 68, speed: 1.6, base: 525, phase: 2 },
      { x: 410, y: 392, w: 36, h: 18, axis: "y", range: 50, speed: 1.2, base: 392, phase: 5 },
      { x: 670, y: 270, w: 42, h: 18, axis: "x", range: 54, speed: 1.8, base: 670, phase: 9 },
      { x: 842, y: 218, w: 40, h: 18, axis: "y", range: 45, speed: 1.4, base: 218, phase: 13 },
      { x: 596, y: 80, w: 36, h: 18, axis: "x", range: 70, speed: 1.7, base: 596, phase: 21 },
    ];

    const goal = { x: 352, y: 70, w: 78, h: 58 };

    const player = {
      x: spawn.x,
      y: spawn.y,
      w: 22,
      h: 31,
      vx: 0,
      vy: 0,
      grounded: false,
      rope: null,
      face: 1,
      deaths: 0,
      won: false,
    };

    let startTime = performance.now();
    let winTime = 0;
    let cameraX = 0;
    let shake = 0;

    function reset(toStart = false) {
      if (toStart) {
        checkpoints.forEach((c, i) => c.got = i === 0);
        currentCheckpoint = checkpoints[0];
        player.deaths = 0;
        startTime = performance.now();
        player.won = false;
        winTime = 0;
      }
      player.x = currentCheckpoint.x;
      player.y = currentCheckpoint.y - player.h;
      player.vx = 0;
      player.vy = 0;
      player.rope = null;
      shake = 12;
    }

    function rects(a, b) {
      return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    function keyDown(e) {
      keys.add(e.key.toLowerCase());
      if ([" ", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(e.key.toLowerCase())) {
        e.preventDefault();
      }
      if (e.key.toLowerCase() === "r") reset(true);
    }
    function keyUp(e) {
      keys.delete(e.key.toLowerCase());
    }
    canvas.addEventListener("keydown", keyDown);
    canvas.addEventListener("keyup", keyUp);
    window.addEventListener("keydown", (e) => {
      if (document.activeElement === canvas) keyDown(e);
    });
    window.addEventListener("keyup", (e) => {
      if (document.activeElement === canvas) keyUp(e);
    });
    canvas.addEventListener("pointerdown", () => canvas.focus());

    function input(name) {
      if (name === "left") return keys.has("arrowleft") || keys.has("a");
      if (name === "right") return keys.has("arrowright") || keys.has("d");
      if (name === "up") return keys.has("arrowup") || keys.has("w") || keys.has(" ");
      if (name === "down") return keys.has("arrowdown") || keys.has("s");
      return false;
    }

    function updateHazards(t) {
      for (const h of hazards) {
        const v = Math.sin(t * 0.001 * h.speed + h.phase) * h.range;
        if (h.axis === "x") h.x = h.base + v;
        else h.y = h.base + v;
      }
    }

    function update() {
      if (player.won) return;

      const prev = { x: player.x, y: player.y, w: player.w, h: player.h };
      player.grounded = false;

      let nearRope = null;
      for (const rope of ropes) {
        if (Math.abs((player.x + player.w / 2) - rope.x) < 20 &&
            player.y + player.h > rope.y &&
            player.y < rope.y + rope.h) {
          nearRope = rope;
          break;
        }
      }

      if ((input("up") || input("down")) && nearRope && !player.grounded) {
        player.rope = nearRope;
      }

      if (player.rope) {
        player.vx = 0;
        player.vy = 0;
        player.x += (player.rope.x - (player.x + player.w / 2)) * 0.22;
        if (input("up")) player.y -= 3.1;
        if (input("down")) player.y += 3.1;
        if (input("left")) {
          player.vx = -3.8;
          player.vy = -3.6;
          player.rope = null;
        }
        if (input("right")) {
          player.vx = 3.8;
          player.vy = -3.6;
          player.rope = null;
        }
        if (!nearRope || player.y < player.rope.y - 12 || player.y > player.rope.y + player.rope.h) {
          player.rope = null;
        }
      } else {
        const accel = player.grounded ? 0.75 : 0.45;
        if (input("left")) {
          player.vx -= accel;
          player.face = -1;
        }
        if (input("right")) {
          player.vx += accel;
          player.face = 1;
        }
        player.vx *= 0.84;
        player.vx = Math.max(-5.2, Math.min(5.2, player.vx));
        player.vy += 0.55;
        player.vy = Math.min(12, player.vy);
      }

      player.x += player.vx;
      player.y += player.vy;

      for (const p of platforms) {
        const top = p.y + Math.sin((player.x - p.x) / Math.max(1, p.w) * Math.PI) * p.tilt;
        const platformRect = { x: p.x, y: top, w: p.w, h: p.h };
        if (rects(player, platformRect)) {
          const wasAbove = prev.y + prev.h <= top + 8;
          const wasBelow = prev.y >= top + p.h - 2;
          if (wasAbove && player.vy >= 0) {
            player.y = top - player.h;
            player.vy = 0;
            player.grounded = true;
            player.rope = null;
          } else if (wasBelow && player.vy < 0) {
            player.y = top + p.h;
            player.vy = 0.7;
          } else if (prev.x + prev.w <= p.x) {
            player.x = p.x - player.w;
            player.vx *= -0.15;
          } else if (prev.x >= p.x + p.w) {
            player.x = p.x + p.w;
            player.vx *= -0.15;
          }
        }
      }

      if (player.grounded && input("up")) {
        player.vy = -11.4;
        player.grounded = false;
      }

      for (const h of hazards) {
        if (rects(player, h)) {
          player.deaths += 1;
          reset(false);
        }
      }

      for (const c of checkpoints) {
        if (!c.got && Math.hypot(player.x - c.x, player.y - c.y) < 45) {
          c.got = true;
          currentCheckpoint = c;
        }
      }

      if (rects(player, goal)) {
        player.won = true;
        winTime = performance.now() - startTime;
      }

      if (player.y > H + 140 || player.x < -120 || player.x > W + 160) {
        player.deaths += 1;
        reset(false);
      }

      cameraX += (Math.max(0, Math.min(W - 980, player.x - 430)) - cameraX) * 0.05;
      shake *= 0.86;
    }

    function wonkyLine(x1, y1, x2, y2, color = "#111", width = 2, steps = 7) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      for (let i = 1; i < steps; i++) {
        const t = i / steps;
        const wobble = Math.sin((x1 + y2 + i) * 12.98) * 3;
        ctx.lineTo(x1 + (x2 - x1) * t + wobble, y1 + (y2 - y1) * t - wobble);
      }
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    function drawTree(x, y, s, ugly) {
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 3;
      ctx.fillStyle = ugly ? "#a06a2b" : "#b27832";
      ctx.fillRect(x - 8 * s, y - 48 * s, 17 * s, 49 * s);
      ctx.strokeRect(x - 8 * s, y - 48 * s, 17 * s, 49 * s);
      ctx.fillStyle = ugly ? "#54d65b" : "#65c84f";
      for (let i = 0; i < 4; i++) {
        ctx.beginPath();
        ctx.arc(x + (i - 1.5) * 17 * s, y - (58 + i * 6) * s, (24 - i * 2) * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.fillStyle = "#fff";
      ctx.fillRect(x + 6 * s, y - 77 * s, 5 * s, 4 * s);
    }

    function drawBackground() {
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = "#e5e5e5";
      ctx.lineWidth = 1;
      for (let x = 0; x < W; x += 28) {
        wonkyLine(x, 0, x + 4, H, "#f1f1f1", 1, 5);
      }
      for (let y = 0; y < H; y += 28) {
        wonkyLine(0, y, W, y + 3, "#f4f4f4", 1, 5);
      }
      drawTree(80, 605, 1.25, true);
      drawTree(235, 612, 0.9, false);
      drawTree(955, 618, 1.1, true);
      drawTree(728, 620, 0.75, false);

      ctx.fillStyle = "#f8f8ff";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2;
      for (const c of [{x:130,y:70},{x:455,y:48},{x:890,y:84}]) {
        ctx.beginPath();
        ctx.ellipse(c.x, c.y, 50, 17, 0.1, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillRect(c.x + 22, c.y - 4, 8, 3);
      }
    }

    function drawPlatform(p, index) {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.tilt * Math.PI / 320);
      ctx.fillStyle = index % 2 ? "#8ce05b" : "#77ca44";
      ctx.fillRect(0, 0, p.w, p.h);
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 3;
      ctx.strokeRect(0, 0, p.w, p.h);
      ctx.fillStyle = "#8b5a2b";
      ctx.fillRect(4, p.h - 5, p.w - 8, 5);
      ctx.strokeStyle = "#5c351a";
      ctx.lineWidth = 2;
      for (let x = 8; x < p.w; x += 23) {
        wonkyLine(x, p.h - 6, x + 8, p.h - 1, "#5c351a", 1, 3);
      }
      ctx.restore();
    }

    function drawRope(r) {
      wonkyLine(r.x, r.y, r.x + 2, r.y + r.h, "#9b5d22", 4, 18);
      for (let y = r.y + 16; y < r.y + r.h; y += 22) {
        wonkyLine(r.x - 9, y, r.x + 10, y + 2, "#111", 2, 4);
      }
    }

    function drawHazard(h, t) {
      ctx.save();
      ctx.translate(h.x + h.w / 2, h.y + h.h / 2);
      ctx.rotate(Math.sin(t * 0.01 + h.phase) * 0.25);
      ctx.fillStyle = "#ff2d2d";
      ctx.fillRect(-h.w / 2, -h.h / 2, h.w, h.h);
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 3;
      ctx.strokeRect(-h.w / 2, -h.h / 2, h.w, h.h);
      ctx.fillStyle = "#fff";
      ctx.fillRect(-h.w / 2 + 7, -4, 5, 5);
      ctx.fillRect(5, -5, 5, 5);
      ctx.restore();
    }

    function drawCheckpoint(c) {
      ctx.strokeStyle = c.got ? "#1ba84c" : "#111";
      ctx.fillStyle = c.got ? "#b7ffba" : "#fff";
      ctx.lineWidth = 3;
      wonkyLine(c.x, c.y - 35, c.x, c.y + 25, ctx.strokeStyle, 3, 5);
      ctx.beginPath();
      ctx.moveTo(c.x, c.y - 35);
      ctx.lineTo(c.x + 32, c.y - 24);
      ctx.lineTo(c.x + 2, c.y - 12);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    function drawGoal() {
      ctx.fillStyle = "#fff56d";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 3;
      ctx.fillRect(goal.x, goal.y, goal.w, goal.h);
      ctx.strokeRect(goal.x, goal.y, goal.w, goal.h);
      ctx.fillStyle = "#111";
      ctx.font = "bold 16px Comic Sans MS, sans-serif";
      ctx.fillText("끝?", goal.x + 23, goal.y + 34);
      ctx.fillStyle = "#ff6fb1";
      ctx.fillRect(goal.x + 9, goal.y + 9, 12, 12);
      ctx.fillRect(goal.x + 58, goal.y + 39, 9, 9);
    }

    function drawPlayer(t) {
      ctx.save();
      ctx.translate(player.x + player.w / 2, player.y + player.h / 2);
      ctx.scale(player.face, 1);
      ctx.rotate(Math.sin(t * 0.012) * (player.grounded ? 0.03 : 0.1));
      ctx.fillStyle = "#ffe0b8";
      ctx.fillRect(-10, -15, 20, 18);
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2;
      ctx.strokeRect(-10, -15, 20, 18);
      ctx.fillStyle = "#4aa3ff";
      ctx.fillRect(-8, 2, 16, 16);
      ctx.strokeRect(-8, 2, 16, 16);
      ctx.fillStyle = "#ff5b92";
      ctx.fillRect(-13, -18, 26, 8);
      ctx.strokeRect(-13, -18, 26, 8);
      ctx.fillStyle = "#111";
      ctx.fillRect(2, -8, 3, 3);
      ctx.fillRect(7, -7, 2, 2);
      ctx.fillRect(-3, -1, 7, 2);
      ctx.fillStyle = "#333";
      ctx.fillRect(-9, 18, 7, 5);
      ctx.fillRect(3, 18, 8, 5);
      ctx.restore();
    }

    function drawUi(t) {
      const elapsed = player.won ? winTime : performance.now() - startTime;
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 3;
      ctx.fillRect(14, 12, 302, 70);
      ctx.strokeRect(14, 12, 302, 70);
      ctx.fillStyle = "#111";
      ctx.font = "bold 20px Comic Sans MS, Malgun Gothic, sans-serif";
      ctx.fillText("이상한 숲 점프", 28, 39);
      ctx.font = "16px Comic Sans MS, Malgun Gothic, sans-serif";
      ctx.fillText("time " + (elapsed / 1000).toFixed(1) + "s   miss " + player.deaths, 28, 64);
      if (player.won) {
        ctx.fillStyle = "rgba(255,255,255,.92)";
        ctx.fillRect(270, 205, 520, 150);
        ctx.strokeStyle = "#111";
        ctx.strokeRect(270, 205, 520, 150);
        ctx.fillStyle = "#111";
        ctx.font = "bold 34px Comic Sans MS, Malgun Gothic, sans-serif";
        ctx.fillText("클리어... 라고 치자", 345, 265);
        ctx.font = "19px Comic Sans MS, Malgun Gothic, sans-serif";
        ctx.fillText("R 키를 누르면 다시 그 못생긴 숲으로 갑니다.", 335, 308);
      }
    }

    function render(t) {
      updateHazards(t);
      update();

      ctx.save();
      const sx = shake ? (Math.random() - 0.5) * shake : 0;
      const sy = shake ? (Math.random() - 0.5) * shake : 0;
      ctx.translate(Math.round(sx), Math.round(sy));
      drawBackground();
      drawGoal();
      ropes.forEach(drawRope);
      platforms.forEach(drawPlatform);
      checkpoints.forEach(drawCheckpoint);
      hazards.forEach(h => drawHazard(h, t));
      drawPlayer(t);
      ctx.restore();
      drawUi(t);

      requestAnimationFrame(render);
    }

    canvas.focus();
    reset(true);
    requestAnimationFrame(render);
  </script>
</body>
</html>
"""

components.html(game_html, height=735, scrolling=False)
