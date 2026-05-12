import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.chat_render import render_style, render_top_navigation  # noqa: E402

st.set_page_config(
    page_title="허접한 인내의 숲",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_style()
st.markdown('<div class="maple-game-page-marker"></div>', unsafe_allow_html=True)
render_top_navigation(active_menu_key="game")

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1040px;
        padding-top: 1.2rem;
    }

    h1 {
        font-size: 1.55rem !important;
        margin-bottom: 0.2rem !important;
    }

    .stCaption {
        margin-bottom: 0.35rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

st.title("허접한 인내의 숲")
st.caption("화살표 또는 WASD 이동, Space 점프")

GAME_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"


def game_asset_path(filename: str) -> Path:
    return GAME_ASSET_DIR / filename


bgm_path = game_asset_path("엘리니아 필드.mp3")
if bgm_path.exists():
    st.audio(bgm_path, format="audio/mpeg", loop=True, autoplay=True, width=320)


def image_to_data_url(path: Path | None = None, uploaded_file=None) -> str:
    if path is not None and path.exists():
        image_bytes = path.read_bytes()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "image/png")
    elif uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        mime_type = uploaded_file.type or "image/png"
    else:
        return ""

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


default_spritesheet = game_asset_path("spritesheet.webp")
default_character = game_asset_path("character.png")
default_exit_portal = game_asset_path("exit_portal.png")
default_background = game_asset_path("elinia.png")
default_star_projectile = game_asset_path("표창.png")
default_npc = game_asset_path("npc.png")
default_ellinia_emblem = game_asset_path("엘리니아엠블렘.png")
default_elixir = game_asset_path("엘릭서.png")
background_data_url = ""
character_data_url = ""
portal_data_url = ""
star_data_url = ""
npc_data_url = ""
ellinia_emblem_data_url = ""
elixir_data_url = ""

if default_background.exists():
    background_data_url = image_to_data_url(default_background)

if default_exit_portal.exists():
    portal_data_url = image_to_data_url(default_exit_portal)

if default_star_projectile.exists():
    star_data_url = image_to_data_url(default_star_projectile)

if default_npc.exists():
    npc_data_url = image_to_data_url(default_npc)

if default_ellinia_emblem.exists():
    ellinia_emblem_data_url = image_to_data_url(default_ellinia_emblem)

if default_elixir.exists():
    elixir_data_url = image_to_data_url(default_elixir)

if default_spritesheet.exists():
    character_data_url = image_to_data_url(default_spritesheet)
elif default_character.exists():
    character_data_url = image_to_data_url(default_character)
else:
    uploaded_character = st.file_uploader(
        "플레이어 캐릭터 이미지",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
    )

    if uploaded_character is not None:
        character_data_url = image_to_data_url(uploaded_file=uploaded_character)
    else:
        st.caption(
            "캐릭터 이미지를 spritesheet.webp 또는 character.png로 저장하거나 여기 업로드하면 "
            "그 캐릭터가 직접 움직입니다."
        )


game_html = """
    <div class="game-shell">
      <canvas id="game" width="960" height="680" aria-label="bad forest platform game"></canvas>
      <div class="hud">
        <button id="restart">처음부터</button>
        <button id="prev-stage">이전</button>
        <button id="next-stage">다음</button>
        <span id="status">대충 시작!</span>
      </div>
    </div>

    <style>
    html, body {
      margin: 0;
      background: #0d1f18;
    }

    .game-shell {
      width: min(960px, 100%);
      margin: 0 auto;
      user-select: none;
      font-family: Arial, sans-serif;
    }

    #game {
      width: 100%;
      aspect-ratio: 24 / 17;
      display: block;
      background: #132f24;
      image-rendering: pixelated;
      border: 1px solid rgba(222, 255, 198, 0.26);
      border-radius: 8px;
      box-sizing: border-box;
      box-shadow:
        0 24px 80px rgba(0, 0, 0, 0.45),
        inset 0 0 0 1px rgba(255, 255, 255, 0.08);
    }

    .hud {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 0 0;
      color: #dff7d5;
      font-size: 14px;
    }

    #status {
      display: none;
    }

    button {
      border: 1px solid rgba(224, 255, 203, 0.35);
      border-radius: 6px;
      background: linear-gradient(#284b34, #14281f);
      color: #eaffdf;
      padding: 5px 10px;
      font-weight: 700;
      cursor: pointer;
    }
    </style>

    <script>
    const canvas = document.getElementById("game");
    const ctx = canvas.getContext("2d");
    const statusText = document.getElementById("status");
    const restartButton = document.getElementById("restart");
    const prevStageButton = document.getElementById("prev-stage");
    const nextStageButton = document.getElementById("next-stage");
    const suppliedBackground = "__BACKGROUND_DATA_URL__";
    const suppliedCharacter = "__CHARACTER_DATA_URL__";
    const suppliedPortal = "__PORTAL_DATA_URL__";
    const suppliedStar = "__STAR_DATA_URL__";
    const suppliedNpc = "__NPC_DATA_URL__";
    const suppliedElliniaEmblem = "__ELLINIA_EMBLEM_DATA_URL__";
    const suppliedElixir = "__ELIXIR_DATA_URL__";
    const backgroundImage = new Image();
    const characterImage = new Image();
    const portalImage = new Image();
    const starImage = new Image();
    const npcImage = new Image();
    const elliniaEmblemImage = new Image();
    const elixirImage = new Image();
    const characterCanvas = document.createElement("canvas");
    const characterCtx = characterCanvas.getContext("2d");
    const spriteFrameCanvas = document.createElement("canvas");
    const spriteFrameCtx = spriteFrameCanvas.getContext("2d", { willReadFrequently: true });
    const starCanvas = document.createElement("canvas");
    const starCtx = starCanvas.getContext("2d", { willReadFrequently: true });
    const npcCanvas = document.createElement("canvas");
    const npcCtx = npcCanvas.getContext("2d", { willReadFrequently: true });
    const elixirCanvas = document.createElement("canvas");
    const elixirCtx = elixirCanvas.getContext("2d", { willReadFrequently: true });
    let hasSuppliedBackground = false;
    let hasCharacterSprite = false;
    let hasPortalImage = false;
    let hasStarImage = false;
    let hasNpcImage = false;
    let hasElliniaEmblem = false;
    let hasElixirImage = false;
    let hasCharacterSheet = false;
    let characterSpriteBounds = { x: 0, y: 0, w: 1, h: 1 };
    let npcSpriteBounds = { x: 0, y: 0, w: 52, h: 70 };

    if (suppliedBackground) {
      backgroundImage.src = suppliedBackground;
      backgroundImage.onload = () => {
        hasSuppliedBackground = true;
      };
    }

    if (suppliedCharacter) {
      characterImage.src = suppliedCharacter;
      characterImage.onload = () => {
        characterCanvas.width = characterImage.naturalWidth;
        characterCanvas.height = characterImage.naturalHeight;
        characterCtx.clearRect(0, 0, characterCanvas.width, characterCanvas.height);
        characterCtx.drawImage(characterImage, 0, 0);
        hasCharacterSheet = characterImage.naturalWidth >= 1400 && characterImage.naturalHeight >= 1600;
        characterSpriteBounds = findOpaqueBounds(
          characterCtx.getImageData(0, 0, characterCanvas.width, characterCanvas.height)
        );
        hasCharacterSprite = true;
      };
    }

    if (suppliedPortal) {
      portalImage.src = suppliedPortal;
      portalImage.onload = () => {
        hasPortalImage = true;
      };
    }

    function makeEdgeWhiteTransparent(imageData) {
      const { width, height, data } = imageData;
      const visited = new Uint8Array(width * height);
      const stack = [];

      function isNearWhite(pixelIndex) {
        const offset = pixelIndex * 4;
        return data[offset + 3] > 0 && data[offset] > 235 && data[offset + 1] > 235 && data[offset + 2] > 235;
      }

      function addPixel(x, y) {
        if (x < 0 || y < 0 || x >= width || y >= height) return;
        const pixelIndex = y * width + x;
        if (visited[pixelIndex] || !isNearWhite(pixelIndex)) return;
        visited[pixelIndex] = 1;
        stack.push(pixelIndex);
      }

      for (let x = 0; x < width; x++) {
        addPixel(x, 0);
        addPixel(x, height - 1);
      }
      for (let y = 0; y < height; y++) {
        addPixel(0, y);
        addPixel(width - 1, y);
      }

      while (stack.length) {
        const pixelIndex = stack.pop();
        const offset = pixelIndex * 4;
        data[offset + 3] = 0;
        const x = pixelIndex % width;
        const y = Math.floor(pixelIndex / width);
        addPixel(x + 1, y);
        addPixel(x - 1, y);
        addPixel(x, y + 1);
        addPixel(x, y - 1);
      }

      return imageData;
    }

    function findOpaqueBounds(imageData) {
      const { width, height, data } = imageData;
      let minX = width;
      let minY = height;
      let maxX = -1;
      let maxY = -1;

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const alpha = data[(y * width + x) * 4 + 3];
          if (alpha <= 18) continue;
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x);
          maxY = Math.max(maxY, y);
        }
      }

      if (maxX < minX || maxY < minY) {
        return { x: 0, y: 0, w: width, h: height };
      }

      return {
        x: minX,
        y: minY,
        w: maxX - minX + 1,
        h: maxY - minY + 1,
      };
    }

    function isSpriteSheetBackdropPixel(data, pixelIndex) {
      const offset = pixelIndex * 4;
      const r = data[offset];
      const g = data[offset + 1];
      const b = data[offset + 2];
      const a = data[offset + 3];
      if (a <= 18) return true;

      const hotMagenta = r >= 120 && g <= 55 && b >= 95;
      const deepPurple = r >= 60 && g <= 35 && b >= 60 && Math.abs(r - b) <= 95;
      const artifactBlue = b >= 150 && r <= 70 && g <= 95;
      const artifactGreen = g >= 85 && r <= 45 && b <= 45;
      const artifactRed = r >= 130 && g <= 35 && b <= 45;
      return hotMagenta || deepPurple || artifactBlue || artifactGreen || artifactRed;
    }

    function makeSpriteSheetBackdropTransparent(imageData) {
      const { width, height, data } = imageData;
      const seen = new Uint8Array(width * height);
      const stack = [];

      function addPixel(x, y) {
        if (x < 0 || y < 0 || x >= width || y >= height) return;
        const pixelIndex = y * width + x;
        if (seen[pixelIndex] || !isSpriteSheetBackdropPixel(data, pixelIndex)) return;
        seen[pixelIndex] = 1;
        stack.push(pixelIndex);
      }

      for (let x = 0; x < width; x++) {
        addPixel(x, 0);
        addPixel(x, height - 1);
      }
      for (let y = 0; y < height; y++) {
        addPixel(0, y);
        addPixel(width - 1, y);
      }

      while (stack.length) {
        const pixelIndex = stack.pop();
        data[pixelIndex * 4 + 3] = 0;
        const x = pixelIndex % width;
        const y = Math.floor(pixelIndex / width);
        addPixel(x + 1, y);
        addPixel(x - 1, y);
        addPixel(x, y + 1);
        addPixel(x, y - 1);
      }

      return imageData;
    }

    function cleanSpriteCell(sprite) {
      spriteFrameCanvas.width = sprite.sw;
      spriteFrameCanvas.height = sprite.sh;
      spriteFrameCtx.clearRect(0, 0, sprite.sw, sprite.sh);
      spriteFrameCtx.drawImage(characterCanvas, sprite.sx, sprite.sy, sprite.sw, sprite.sh, 0, 0, sprite.sw, sprite.sh);
      const pixels = spriteFrameCtx.getImageData(0, 0, sprite.sw, sprite.sh);
      spriteFrameCtx.putImageData(makeSpriteSheetBackdropTransparent(pixels), 0, 0);
      return findOpaqueBounds(spriteFrameCtx.getImageData(0, 0, sprite.sw, sprite.sh));
    }

    function buildStarProjectile() {
      const crop = { x: 386, y: 34, w: 160, h: 154 };
      const size = 72;
      starCanvas.width = size;
      starCanvas.height = size;
      starCtx.clearRect(0, 0, size, size);
      starCtx.imageSmoothingEnabled = false;
      starCtx.drawImage(starImage, crop.x, crop.y, crop.w, crop.h, 0, 0, size, size);
      const pixels = starCtx.getImageData(0, 0, size, size);
      starCtx.putImageData(makeEdgeWhiteTransparent(pixels), 0, 0);
      hasStarImage = true;
    }

    if (suppliedStar) {
      starImage.src = suppliedStar;
      starImage.onload = buildStarProjectile;
    }

    if (suppliedNpc) {
      npcImage.src = suppliedNpc;
      npcImage.onload = () => {
        npcCanvas.width = npcImage.naturalWidth;
        npcCanvas.height = npcImage.naturalHeight;
        npcCtx.clearRect(0, 0, npcCanvas.width, npcCanvas.height);
        npcCtx.drawImage(npcImage, 0, 0);
        npcSpriteBounds = findOpaqueBounds(npcCtx.getImageData(0, 0, npcCanvas.width, npcCanvas.height));
        hasNpcImage = true;
      };
    }

    if (suppliedElliniaEmblem) {
      elliniaEmblemImage.src = suppliedElliniaEmblem;
      elliniaEmblemImage.onload = () => {
        hasElliniaEmblem = true;
      };
    }

    if (suppliedElixir) {
      elixirImage.src = suppliedElixir;
      elixirImage.onload = () => {
        elixirCanvas.width = elixirImage.naturalWidth;
        elixirCanvas.height = elixirImage.naturalHeight;
        elixirCtx.clearRect(0, 0, elixirCanvas.width, elixirCanvas.height);
        elixirCtx.drawImage(elixirImage, 0, 0);
        const pixels = elixirCtx.getImageData(0, 0, elixirCanvas.width, elixirCanvas.height);
        elixirCtx.putImageData(makeEdgeWhiteTransparent(pixels), 0, 0);
        hasElixirImage = true;
      };
    }

    ctx.imageSmoothingEnabled = false;

    const keys = new Set();
    const world = { width: 960, height: 1650, gravity: 0.55 };
    const classicHudHeight = 96;
    const spriteGrid = {
      x: [0, 200, 400, 600, 800, 1000, 1200, 1366],
      y: [0, 210, 420, 630, 835, 1040, 1260, 1460, 1660],
      w: 170,
      h: 190,
    };

    function normalizeKey(event) {
      if (event.code === "Space") return " ";
      if (event.code === "ShiftLeft" || event.code === "ShiftRight") return "Shift";
      if (event.code === "KeyA") return "a";
      if (event.code === "KeyD") return "d";
      if (event.code === "KeyW") return "w";
      if (event.code === "KeyS") return "s";
      return event.key;
    }
    const spriteBoundsCache = new Map();

    function spriteCell(row, col) {
      return {
        sx: spriteGrid.x[col],
        sy: spriteGrid.y[row],
        sw: spriteGrid.w,
        sh: spriteGrid.h,
      };
    }

    const spriteAnimations = {
      idle: [
        spriteCell(0, 0),
        spriteCell(0, 1),
        spriteCell(0, 2),
        spriteCell(0, 3),
        spriteCell(0, 4),
        spriteCell(0, 5),
      ],
      run: [
        spriteCell(1, 0),
        spriteCell(1, 1),
        spriteCell(1, 2),
        spriteCell(1, 3),
        spriteCell(1, 4),
        spriteCell(1, 5),
        spriteCell(1, 6),
        spriteCell(1, 7),
        spriteCell(2, 0),
        spriteCell(2, 1),
        spriteCell(2, 2),
        spriteCell(2, 3),
        spriteCell(2, 4),
        spriteCell(2, 5),
        spriteCell(2, 6),
        spriteCell(2, 7),
      ],
      jump: [
        spriteCell(0, 0),
      ],
      rope: [
        spriteCell(3, 0),
        spriteCell(3, 1),
        spriteCell(3, 2),
        spriteCell(3, 3),
      ],
      fall: [
        spriteCell(0, 5),
      ],
      crouch: [
        spriteCell(5, 0),
        spriteCell(5, 1),
        spriteCell(5, 7),
      ],
    };

    const npcStageMessages = [
      [
        "천천히 가. 급하면 바로 떨어진다.",
        "점프는 끝까지 누르면 조금 더 높아.",
        "발판 가운데를 보고 착지해.",
        "괜찮아. 처음 숲은 몸풀기야.",
      ],
      [
        "창은 타이밍만 보면 지나갈 수 있어.",
        "튀어나온 뒤 들어갈 때가 기회야.",
        "표창보다 창 소리를 먼저 봐.",
        "서두르지 말고 한 칸씩.",
      ],
      [
        "표창 리듬을 보고 뛰어.",
        "좁은 발판은 멈춰서 숨 고르자.",
        "떨어질 것 같으면 반대로 살짝.",
        "여긴 손보다 침착함 싸움이야.",
      ],
      [
        "여기부터 손이 좀 바빠질 거야.",
        "표창 지나간 직후가 제일 편해.",
        "멀리 뛰기 전에 착지점을 먼저 봐.",
        "급한 점프는 숲이 다 받아먹는다.",
      ],
      [
        "마지막이야. 침착하게 한 발씩.",
        "작은 발판은 짧게 눌러.",
        "창이 들어간 순간 바로 넘어가.",
        "여기 깨면 진짜 인내 인정.",
      ],
    ];

    const stages = [
      {
        name: "인내의 숲 <1단계>: 끊긴 발판",
        height: 1650,
        tint: "#dfffd1",
        start: { x: 78, y: 1546 },
        goal: { x: 720, y: 54, w: 160, h: 90 },
        checkpoints: [
          { x: 590, y: 1016, w: 22, h: 45 },
          { x: 116, y: 698, w: 22, h: 45 },
          { x: 520, y: 390, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [],
        platforms: [
          { x: 42, y: 1600, w: 190, h: 15 },
          { x: 248, y: 1538, w: 160, h: 14 },
          { x: 450, y: 1472, w: 160, h: 14 },
          { x: 650, y: 1404, w: 160, h: 14 },
          { x: 500, y: 1324, w: 155, h: 14 },
          { x: 310, y: 1248, w: 155, h: 14 },
          { x: 116, y: 1170, w: 150, h: 14 },
          { x: 338, y: 1096, w: 150, h: 14 },
          { x: 588, y: 1020, w: 150, h: 14 },
          { x: 762, y: 940, w: 140, h: 14 },
          { x: 546, y: 858, w: 145, h: 14 },
          { x: 326, y: 780, w: 145, h: 14 },
          { x: 112, y: 702, w: 140, h: 14 },
          { x: 344, y: 628, w: 140, h: 14 },
          { x: 584, y: 552, w: 140, h: 14 },
          { x: 748, y: 474, w: 136, h: 14 },
          { x: 520, y: 394, w: 136, h: 14 },
          { x: 294, y: 316, w: 132, h: 14 },
          { x: 520, y: 236, w: 132, h: 14 },
          { x: 752, y: 146, w: 140, h: 14 },
        ],
        hazards: [
          { x: 492, y: 1288, r: 11, dx: 1.25, min: 360, max: 700, type: "star" },
          { x: 650, y: 246, r: 11, dx: -1.15, min: 548, max: 840, type: "star" },
        ],
      },
      {
        name: "인내의 숲 <2단계>: 창과 투사체",
        height: 1780,
        tint: "#c7ffd8",
        start: { x: 812, y: 1670 },
        goal: { x: 54, y: 55, w: 160, h: 90 },
        checkpoints: [
          { x: 744, y: 1276, w: 22, h: 45 },
          { x: 274, y: 518, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [
          { platform: 4, dir: "up", align: 0.55, span: 64, length: 42, phase: 30, period: 165 },
          { platform: 8, dir: "up", align: 0.48, span: 54, length: 44, phase: 70, period: 160 },
          { platform: 12, dir: "up", align: 0.52, span: 58, length: 44, phase: 110, period: 155 },
        ],
        platforms: [
          { x: 748, y: 1720, w: 172, h: 15 },
          { x: 545, y: 1612, w: 132, h: 14 },
          { x: 332, y: 1508, w: 128, h: 14 },
          { x: 590, y: 1392, w: 126, h: 14 },
          { x: 750, y: 1280, w: 118, h: 14 },
          { x: 514, y: 1182, w: 116, h: 14 },
          { x: 274, y: 1088, w: 118, h: 14 },
          { x: 74, y: 990, w: 118, h: 14 },
          { x: 240, y: 900, w: 112, h: 14 },
          { x: 470, y: 812, w: 112, h: 14 },
          { x: 710, y: 724, w: 108, h: 14 },
          { x: 512, y: 612, w: 110, h: 14 },
          { x: 272, y: 522, w: 106, h: 14 },
          { x: 64, y: 430, w: 106, h: 14 },
          { x: 260, y: 340, w: 100, h: 14 },
          { x: 530, y: 258, w: 100, h: 14 },
          { x: 300, y: 206, w: 100, h: 14 },
          { x: 52, y: 148, w: 150, h: 14 },
        ],
        hazards: [
          { x: 720, y: 1568, r: 12, dx: -1.55, min: 420, max: 860, type: "star" },
          { x: 166, y: 928, r: 12, dx: 1.45, min: 42, max: 510, type: "star" },
          { x: 778, y: 686, r: 12, dx: -1.5, min: 510, max: 884, type: "star" },
          { x: 520, y: 214, r: 11, dx: 1.35, min: 260, max: 780, type: "star" },
        ],
      },
      {
        name: "인내의 숲 <3단계>: 엇박자 가지길",
        height: 1720,
        tint: "#eaffbd",
        start: { x: 72, y: 1610 },
        goal: { x: 724, y: 58, w: 160, h: 90 },
        checkpoints: [
          { x: 566, y: 1238, w: 22, h: 45 },
          { x: 318, y: 624, w: 22, h: 45 },
          { x: 640, y: 186, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [
          { platform: 2, dir: "up", align: 0.44, span: 58, length: 46, phase: 0, period: 150 },
          { platform: 6, dir: "up", align: 0.52, span: 54, length: 48, phase: 55, period: 148 },
          { platform: 10, dir: "up", align: 0.46, span: 52, length: 48, phase: 102, period: 146 },
          { platform: 13, dir: "up", align: 0.5, span: 50, length: 48, phase: 20, period: 142 },
        ],
        platforms: [
          { x: 38, y: 1660, w: 170, h: 15 },
          { x: 268, y: 1544, w: 124, h: 14 },
          { x: 532, y: 1442, w: 118, h: 14 },
          { x: 724, y: 1324, w: 108, h: 14 },
          { x: 518, y: 1242, w: 108, h: 14 },
          { x: 298, y: 1156, w: 102, h: 14 },
          { x: 90, y: 1068, w: 104, h: 14 },
          { x: 316, y: 978, w: 100, h: 14 },
          { x: 574, y: 892, w: 100, h: 14 },
          { x: 760, y: 806, w: 98, h: 14 },
          { x: 526, y: 716, w: 98, h: 14 },
          { x: 286, y: 628, w: 96, h: 14 },
          { x: 80, y: 540, w: 96, h: 14 },
          { x: 312, y: 450, w: 92, h: 14 },
          { x: 564, y: 360, w: 92, h: 14 },
          { x: 742, y: 270, w: 96, h: 14 },
          { x: 610, y: 190, w: 86, h: 14 },
          { x: 710, y: 160, w: 178, h: 14 },
        ],
        hazards: [
          { x: 330, y: 1490, r: 12, dx: 1.75, min: 242, max: 760, type: "star" },
          { x: 188, y: 1036, r: 12, dx: 1.9, min: 72, max: 472, type: "star" },
          { x: 650, y: 860, r: 13, dx: -1.85, min: 320, max: 860, type: "star" },
          { x: 452, y: 580, r: 12, dx: -1.95, min: 128, max: 720, type: "star" },
          { x: 610, y: 318, r: 12, dx: 1.7, min: 300, max: 850, type: "star" },
          { x: 780, y: 246, r: 11, dx: -1.45, min: 610, max: 900, type: "star" },
        ],
      },
      {
        name: "인내의 숲 <4단계>: 표창 순찰층",
        height: 1700,
        tint: "#d5ffc8",
        start: { x: 820, y: 1588 },
        goal: { x: 68, y: 58, w: 160, h: 90 },
        checkpoints: [
          { x: 650, y: 1264, w: 22, h: 45 },
          { x: 594, y: 582, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [
          { platform: 3, dir: "up", align: 0.45, span: 52, length: 50, phase: 20, period: 128 },
          { platform: 5, dir: "up", align: 0.55, span: 54, length: 50, phase: 68, period: 124 },
          { platform: 8, dir: "up", align: 0.5, span: 52, length: 52, phase: 104, period: 120 },
          { platform: 11, dir: "up", align: 0.5, span: 50, length: 52, phase: 12, period: 118 },
          { platform: 14, dir: "up", align: 0.48, span: 48, length: 50, phase: 82, period: 116 },
        ],
        platforms: [
          { x: 748, y: 1640, w: 170, h: 15 },
          { x: 598, y: 1530, w: 102, h: 14 },
          { x: 744, y: 1408, w: 86, h: 14 },
          { x: 650, y: 1268, w: 84, h: 14 },
          { x: 430, y: 1160, w: 84, h: 14 },
          { x: 196, y: 1050, w: 82, h: 14 },
          { x: 52, y: 940, w: 82, h: 14 },
          { x: 268, y: 846, w: 78, h: 14 },
          { x: 512, y: 760, w: 78, h: 14 },
          { x: 742, y: 674, w: 76, h: 14 },
          { x: 594, y: 586, w: 74, h: 14 },
          { x: 372, y: 500, w: 74, h: 14 },
          { x: 148, y: 414, w: 72, h: 14 },
          { x: 328, y: 330, w: 70, h: 14 },
          { x: 562, y: 246, w: 70, h: 14 },
          { x: 304, y: 210, w: 70, h: 14 },
          { x: 52, y: 150, w: 180, h: 14 },
        ],
        hazards: [
          { x: 602, y: 1470, r: 13, dx: -2.15, min: 320, max: 880, type: "star" },
          { x: 140, y: 1220, r: 13, dx: 2.05, min: 70, max: 420, type: "star" },
          { x: 560, y: 864, r: 13, dx: -2.0, min: 216, max: 880, type: "star" },
          { x: 318, y: 706, r: 12, dx: 2.0, min: 76, max: 780, type: "star" },
          { x: 756, y: 418, r: 12, dx: -1.9, min: 520, max: 900, type: "star" },
          { x: 310, y: 214, r: 12, dx: 2.0, min: 52, max: 660, type: "star" },
          { x: 470, y: 1110, r: 11, dy: 1.55, minY: 990, maxY: 1228, type: "star" },
          { x: 690, y: 640, r: 11, dy: -1.65, minY: 526, maxY: 760, type: "star" },
        ],
      },
      {
        name: "인내의 숲 <5단계>: 허브 무더기",
        height: 1900,
        tint: "#ecffd2",
        ascentShrink: true,
        start: { x: 70, y: 1798 },
        goal: { x: 680, y: 58, w: 190, h: 100 },
        checkpoints: [
          { x: 340, y: 1760, w: 22, h: 45, platform: 1 },
          { x: 340, y: 1248, w: 22, h: 45 },
          { x: 546, y: 516, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [
          { platform: 2, dir: "up", align: 0.5, span: 56, length: 48, phase: 0, period: 132 },
          { platform: 4, dir: "up", align: 0.56, span: 54, length: 50, phase: 46, period: 126 },
          { platform: 6, dir: "up", align: 0.44, span: 50, length: 50, phase: 88, period: 124 },
          { platform: 8, dir: "up", align: 0.54, span: 48, length: 52, phase: 118, period: 120 },
          { platform: 10, dir: "up", align: 0.48, span: 46, length: 52, phase: 30, period: 118 },
          { platform: 13, dir: "up", align: 0.5, span: 42, length: 50, phase: 92, period: 116 },
          { platform: 16, dir: "up", align: 0.5, span: 38, length: 48, phase: 145, period: 114 },
          { platform: 19, dir: "up", align: 0.52, span: 34, length: 46, phase: 64, period: 112 },
        ],
        platforms: [
          { x: 42, y: 1848, w: 190, h: 15 },
          { x: 279, y: 1764, w: 172, h: 14 },
          { x: 520, y: 1682, w: 158, h: 14 },
          { x: 750, y: 1592, w: 146, h: 14 },
          { x: 530, y: 1504, w: 136, h: 14 },
          { x: 306, y: 1420, w: 128, h: 14 },
          { x: 85, y: 1338, w: 120, h: 14 },
          { x: 304, y: 1252, w: 112, h: 14 },
          { x: 541, y: 1172, w: 106, h: 14 },
          { x: 754, y: 1088, w: 100, h: 14 },
          { x: 548, y: 1006, w: 94, h: 14 },
          { x: 326, y: 924, w: 88, h: 14 },
          { x: 108, y: 842, w: 84, h: 14 },
          { x: 340, y: 762, w: 80, h: 14 },
          { x: 572, y: 680, w: 76, h: 14 },
          { x: 764, y: 598, w: 72, h: 14 },
          { x: 546, y: 518, w: 68, h: 14 },
          { x: 328, y: 440, w: 64, h: 14 },
          { x: 120, y: 362, w: 60, h: 14 },
          { x: 349, y: 286, w: 58, h: 14 },
          { x: 578, y: 216, w: 56, h: 14 },
          { x: 715, y: 160, w: 150, h: 14 },
        ],
        hazards: [
          { x: 604, y: 1638, r: 11, dx: -2.25, min: 328, max: 870, type: "star" },
          { x: 174, y: 1304, r: 11, dx: 2.12, min: 58, max: 548, type: "star" },
          { x: 764, y: 1054, r: 11, dx: -2.18, min: 432, max: 884, type: "star" },
          { x: 306, y: 808, r: 10, dx: 2.08, min: 70, max: 612, type: "star" },
          { x: 634, y: 562, r: 10, dx: -2.0, min: 382, max: 858, type: "star" },
          { x: 416, y: 326, r: 10, dx: 1.92, min: 96, max: 706, type: "star" },
          { x: 462, y: 1510, r: 10, dy: 1.7, minY: 1376, maxY: 1660, type: "star" },
          { x: 720, y: 960, r: 10, dy: -1.82, minY: 804, maxY: 1118, type: "star" },
          { x: 214, y: 662, r: 10, dy: 1.74, minY: 520, maxY: 844, type: "star" },
          { x: 508, y: 238, r: 9, dy: -1.55, minY: 156, maxY: 360, type: "star" },
        ],
      },
      {
        name: "히든 <6단계>: 극한의 도전",
        height: 2220,
        tint: "#f3d1ff",
        ascentShrink: true,
        looseCheckpoints: true,
        hidden: true,
        start: { x: 70, y: 2118 },
        goal: { x: 704, y: 54, w: 166, h: 96 },
        checkpoints: [
          { x: 294, y: 1606, w: 22, h: 45 },
          { x: 662, y: 956, w: 22, h: 45 },
          { x: 254, y: 356, w: 22, h: 45 },
        ],
        ropes: [],
        spikes: [
          { platform: 2, align: 0.5, span: 34, length: 48, phase: 0, period: 104 },
          { platform: 4, align: 0.48, span: 32, length: 52, phase: 36, period: 102 },
          { platform: 6, align: 0.52, span: 32, length: 52, phase: 68, period: 100 },
          { platform: 8, align: 0.5, span: 30, length: 54, phase: 92, period: 98 },
          { platform: 10, align: 0.48, span: 30, length: 54, phase: 18, period: 96 },
          { platform: 12, align: 0.52, span: 28, length: 52, phase: 52, period: 94 },
          { platform: 14, align: 0.5, span: 28, length: 50, phase: 80, period: 92 },
          { platform: 17, align: 0.5, span: 26, length: 50, phase: 32, period: 90 },
          { platform: 20, align: 0.5, span: 26, length: 48, phase: 72, period: 88 },
        ],
        platforms: [
          { x: 42, y: 2168, w: 178, h: 15 },
          { x: 292, y: 2078, w: 58, h: 14 },
          { x: 524, y: 1988, w: 54, h: 14 },
          { x: 760, y: 1892, w: 52, h: 14 },
          { x: 610, y: 1796, w: 50, h: 14 },
          { x: 360, y: 1704, w: 48, h: 14 },
          { x: 128, y: 1608, w: 48, h: 14 },
          { x: 342, y: 1514, w: 46, h: 14 },
          { x: 590, y: 1424, w: 46, h: 14 },
          { x: 790, y: 1328, w: 44, h: 14 },
          { x: 548, y: 1238, w: 44, h: 14 },
          { x: 312, y: 1148, w: 42, h: 14 },
          { x: 88, y: 1058, w: 42, h: 14 },
          { x: 318, y: 968, w: 40, h: 14 },
          { x: 568, y: 878, w: 40, h: 14 },
          { x: 784, y: 788, w: 40, h: 14 },
          { x: 540, y: 698, w: 38, h: 14 },
          { x: 306, y: 608, w: 38, h: 14 },
          { x: 112, y: 518, w: 38, h: 14 },
          { x: 340, y: 432, w: 36, h: 14 },
          { x: 584, y: 342, w: 36, h: 14 },
          { x: 732, y: 252, w: 36, h: 14 },
          { x: 704, y: 150, w: 150, h: 14 },
        ],
        hazards: [
          { x: 610, y: 2038, r: 10, dx: -2.45, min: 286, max: 842, type: "star" },
          { x: 168, y: 1852, r: 10, dx: 2.35, min: 58, max: 546, type: "star" },
          { x: 792, y: 1662, r: 10, dx: -2.4, min: 404, max: 890, type: "star" },
          { x: 274, y: 1468, r: 10, dx: 2.28, min: 66, max: 650, type: "star" },
          { x: 660, y: 1284, r: 10, dx: -2.3, min: 320, max: 884, type: "star" },
          { x: 210, y: 1014, r: 9, dx: 2.18, min: 54, max: 628, type: "star" },
          { x: 624, y: 744, r: 9, dx: -2.05, min: 298, max: 874, type: "star" },
          { x: 410, y: 392, r: 9, dx: 2.0, min: 76, max: 770, type: "star" },
          { x: 454, y: 1840, r: 9, dy: 1.85, minY: 1668, maxY: 2040, type: "star" },
          { x: 718, y: 1120, r: 9, dy: -1.9, minY: 858, maxY: 1328, type: "star" },
          { x: 206, y: 620, r: 9, dy: 1.82, minY: 426, maxY: 888, type: "star" },
        ],
      },
    ];

    const platformWidthRules = [
      { scale: 1.00, min: 132, max: 190 },
      { scale: 0.88, min: 96, max: 150 },
      { scale: 0.76, min: 78, max: 126 },
      { scale: 0.63, min: 58, max: 108 },
      { scale: 0.72, min: 38, max: 118 },
      { scale: 0.92, min: 30, max: 52 },
    ];

    const platformGuardRules = [
      { step: 9, max: 0, targetTotal: 2, r: 9, speed: 1.0, range: 64, yOffset: 58 },
      { step: 5, max: 1, targetTotal: 4, r: 10, speed: 1.25, range: 82, yOffset: 57 },
      { step: 4, max: 1, targetTotal: 6, r: 10, speed: 1.45, range: 94, yOffset: 56 },
      { step: 3, max: 2, targetTotal: 9, r: 11, speed: 1.62, range: 108, yOffset: 55 },
      { step: 3, max: 2, targetTotal: 11, r: 10, speed: 1.82, range: 118, yOffset: 54 },
      { step: 2, max: 4, targetTotal: 15, r: 9, speed: 2.0, range: 132, yOffset: 52 },
    ];

    const visibleStageCount = 5;
    const hiddenStageIndex = 5;
    const hiddenClearLimitMs = 180000;

    const platformGrassBottomOffset = -3;

    function platformSurfaceY(platform) {
      return platform.y + platformGrassBottomOffset;
    }

    function preparePlatforms(stageConfig, stageIndex) {
      const rule = platformWidthRules[Math.min(stageIndex, platformWidthRules.length - 1)];
      const scaledPlatforms = stageConfig.platforms.map((platform) => {
        const centerX = platform.x + platform.w / 2;
        const ascentProgress = Math.max(0, Math.min(1, 1 - platform.y / stageConfig.height));
        const ascentScale = stageConfig.ascentShrink ? 1 - ascentProgress * 0.38 : 1;
        const width = Math.round(Math.max(rule.min, Math.min(rule.max, platform.w * rule.scale * ascentScale)));
        return {
          ...platform,
          x: Math.round(centerX - width / 2),
          w: width,
        };
      });
      return [
        ...scaledPlatforms,
        { x: 0, y: stageConfig.height - 32, w: world.width, h: 28, floor: true },
      ];
    }

    function findNearestPlatformIndex(checkpoint, stagePlatforms) {
      const centerX = checkpoint.x + checkpoint.w / 2;
      const surfaceHint = checkpoint.y + 1;
      let bestIndex = 0;
      let bestScore = Infinity;

      for (let index = 0; index < stagePlatforms.length; index++) {
        const platform = stagePlatforms[index];
        const platformCenterX = platform.x + platform.w / 2;
        const dx = Math.max(0, Math.abs(centerX - platformCenterX) - platform.w / 2);
        const dy = Math.abs(platformSurfaceY(platform) - surfaceHint);
        const score = dy * 3 + dx;
        if (score < bestScore) {
          bestIndex = index;
          bestScore = score;
        }
      }

      return bestIndex;
    }

    function prepareCheckpoints(stageConfig, stagePlatforms) {
      return stageConfig.checkpoints.map((checkpoint) => {
        const platformIndex = checkpoint.platform ?? findNearestPlatformIndex(checkpoint, stagePlatforms);
        const platform = stagePlatforms[platformIndex];
        if (!platform) return { ...checkpoint };

        if (stageConfig.looseCheckpoints) {
          return {
            ...checkpoint,
            platform: platformIndex,
            x: Math.round(Math.max(platform.x - 12, Math.min(platform.x + platform.w - checkpoint.w + 12, checkpoint.x))),
            y: Math.round(platformSurfaceY(platform) - 1),
          };
        }

        return {
          ...checkpoint,
          platform: platformIndex,
          x: Math.round(platform.x + platform.w / 2 - checkpoint.w / 2),
          y: Math.round(platformSurfaceY(platform) - 1),
        };
      });
    }

    function checkpointPlatformSet(checkpointList) {
      return new Set(checkpointList.map((checkpoint) => checkpoint.platform).filter((platform) => platform !== undefined));
    }

    function hazardBlocksEarlyCheckpoint(hazard, checkpointList) {
      return checkpointList.some((checkpoint) => {
        const checkpointCenterX = checkpoint.x + checkpoint.w / 2;
        const checkpointSurface = checkpoint.y + 1;
        const minX = hazard.min ?? hazard.x - (hazard.r || 0);
        const maxX = hazard.max ?? hazard.x + (hazard.r || 0);
        const minY = hazard.minY ?? hazard.y - (hazard.r || 0);
        const maxY = hazard.maxY ?? hazard.y + (hazard.r || 0);
        const crossesX = checkpointCenterX >= minX - 48 && checkpointCenterX <= maxX + 48;
        const crossesY = checkpointSurface >= minY - 96 && checkpointSurface <= maxY + 96;
        return crossesX && crossesY;
      });
    }

    function prepareHazards(stageConfig, stageIndex, stagePlatforms, checkpointList) {
      const baseHazards = stageConfig.hazards.map((hazard) => ({ ...hazard }));
      const rule = platformGuardRules[Math.min(stageIndex, platformGuardRules.length - 1)];
      const targetTotal = rule.targetTotal;
      const pinnedHazards = baseHazards.filter((hazard) => hazard.pinned);
      const safeCheckpointPlatforms = stageIndex < 2 ? checkpointPlatformSet(checkpointList) : new Set();
      const roamingHazards = baseHazards.filter((hazard) => !hazard.pinned && (stageIndex >= 2 || !hazardBlocksEarlyCheckpoint(hazard, checkpointList)));
      const baseCount = Math.max(0, Math.min(roamingHazards.length, targetTotal - rule.max - pinnedHazards.length));
      const keptBaseHazards = [...roamingHazards.slice(0, baseCount), ...pinnedHazards];
      const guardCount = Math.max(0, Math.min(rule.max, targetTotal - keptBaseHazards.length));
      const guardPlatforms = stagePlatforms
        .map((platform, index) => ({ platform, index }))
        .filter(({ index }) => index > 0 && index < stagePlatforms.length - 1 && index % rule.step === 0 && !safeCheckpointPlatforms.has(index))
        .slice(0, guardCount);

      const guardHazards = guardPlatforms.map(({ platform, index }, guardIndex) => {
        const min = Math.max(28, Math.round(platform.x - rule.range));
        const max = Math.min(world.width - 28, Math.round(platform.x + platform.w + rule.range));
        const direction = (guardIndex + stageIndex) % 2 === 0 ? 1 : -1;
        const speed = rule.speed + (guardIndex % 3) * 0.16;
        const startX = Math.max(min + rule.r, Math.min(max - rule.r, Math.round(platform.x + platform.w / 2 + direction * platform.w * 0.32)));

        return {
          x: startX,
          y: Math.max(92, Math.round(platform.y - rule.yOffset)),
          r: rule.r,
          dx: direction * speed,
          min,
          max,
          type: "star",
          platformGuard: true,
        };
      });

      return [...keptBaseHazards, ...guardHazards];
    }

    function prepareSpikes(stageConfig, stageIndex, stagePlatforms, checkpointList) {
      const safeCheckpointPlatforms = stageIndex < 4 ? checkpointPlatformSet(checkpointList) : new Set();
      return (stageConfig.spikes || []).filter((spike) => !safeCheckpointPlatforms.has(spike.platform)).map((spike) => {
        if (spike.platform === undefined) return { ...spike };

        const platform = stagePlatforms[spike.platform];
        if (!platform) return { ...spike };

        const span = Math.round(Math.min(spike.span || platform.w, platform.w + 12));
        const align = spike.align ?? 0.5;
        const centerX = platform.x + platform.w * align;
        const x = Math.round(Math.max(platform.x - 6, Math.min(platform.x + platform.w + 6 - span, centerX - span / 2)));
        const y = platformSurfaceY(platform);

        return {
          ...spike,
          dir: "up",
          x,
          y,
          w: span,
          h: 24,
        };
      });
    }

    let currentStage = 0;
    let stage = stages[currentStage];
    let platforms = preparePlatforms(stage, currentStage);
    let checkpoints = prepareCheckpoints(stage, platforms);
    let hazards = prepareHazards(stage, currentStage, platforms, checkpoints);
    let ropes = stage.ropes || [];
    let spikes = prepareSpikes(stage, currentStage, platforms, checkpoints);
    let clearTimer = 0;
    let frame = 0;
    let cameraY = 0;
    let stageStartedAt = performance.now();
    let stageFinishElapsedMs = null;
    let stageResults = Array(stages.length).fill(null);
    let hiddenUnlocked = false;
    let resultButtonRect = null;
    let gameOver = false;
    let gameOverFrame = 0;
    let gameOverSpot = { x: 0, y: 0 };
    let gameOverButtonRect = null;
    let checkpointHealReadyAt = new Map();
    let mpWarnFrame = -9999;
    let npcBubbleText = "";
    let npcBubbleMessageIndex = -1;
    let npcBubbleStartFrame = -9999;
    let npcBubbleNextFrame = 0;
    const npcBubbleVisibleFrames = 135;
    const npcBubbleHiddenFrames = 80;

    const player = {
      x: stage.start.x,
      y: stage.start.y,
      w: 22,
      h: 34,
      vx: 0,
      vy: 0,
      grounded: false,
      checkpoint: { ...stage.start },
      checkpointKey: "start",
      deaths: 0,
      hp: 705,
      maxHp: 705,
      mp: 2423,
      maxMp: 2423,
      onRope: false,
      crouching: false,
      facing: 1,
      invuln: 0,
      hitStun: 0,
      fallStartY: null,
      fallFocusFrames: 0,
      focusGlide: false,
      coyote: 0,
      jumpBuffer: 0,
      lastJump: false,
      won: false
    };

    function getStageStartSpot() {
      const startPlatform = platforms[0];
      if (currentStage === hiddenStageIndex && startPlatform) {
        const npcCenterX = getStartNpcCenterX(Math.round(npcSpriteBounds.w * 1.08));
        return {
          x: Math.round(npcCenterX - player.w / 2),
          y: Math.round(platformSurfaceY(startPlatform) - player.h),
        };
      }

      return {
        x: stage.start.x,
        y: startPlatform ? Math.round(platformSurfaceY(startPlatform) - player.h) : stage.start.y,
      };
    }

    function loadStage(index, forceHidden = false) {
      if (index === hiddenStageIndex && !forceHidden && !hiddenUnlocked) {
        statusText.textContent = "히든 스테이지는 조건 달성 시에만 입장 가능";
        return;
      }

      const selectableCount = forceHidden ? stages.length : visibleStageCount;
      currentStage = (index + selectableCount) % selectableCount;
      stage = stages[currentStage];
      world.height = stage.height;
      platforms = preparePlatforms(stage, currentStage);
      checkpoints = prepareCheckpoints(stage, platforms);
      hazards = prepareHazards(stage, currentStage, platforms, checkpoints);
      ropes = stage.ropes || [];
      spikes = prepareSpikes(stage, currentStage, platforms, checkpoints);
      clearTimer = 0;
      stageStartedAt = performance.now();
      stageFinishElapsedMs = null;
      resultButtonRect = null;
      gameOverButtonRect = null;
      checkpointHealReadyAt = new Map();
      mpWarnFrame = -9999;
      gameOver = false;
      gameOverFrame = 0;
      npcBubbleText = "";
      npcBubbleMessageIndex = -1;
      npcBubbleStartFrame = -9999;
      npcBubbleNextFrame = frame;
      const startSpot = getStageStartSpot();
      const playHeight = canvas.height - classicHudHeight;
      cameraY = Math.max(0, Math.min(world.height - playHeight, startSpot.y - playHeight * 0.65));
      player.checkpoint = { ...startSpot };
      player.checkpointKey = "start";
      player.deaths = 0;
      player.hp = player.maxHp;
      player.mp = player.maxMp;
      if (index === 0 && !forceHidden) {
        stageResults = Array(stages.length).fill(null);
        hiddenUnlocked = false;
      }
      reset(false);
      statusText.textContent = `${stage.name} 시작`;
    }

    function loadVisibleStage(index) {
      loadStage((index + visibleStageCount) % visibleStageCount);
    }

    function reset(toCheckpoint = true) {
      const spot = toCheckpoint ? player.checkpoint : getStageStartSpot();
      player.x = spot.x;
      player.y = spot.y;
      player.vx = 0;
      player.vy = 0;
      player.onRope = false;
      player.crouching = false;
      player.invuln = 0;
      player.hitStun = 0;
      player.fallStartY = null;
      player.fallFocusFrames = 0;
      player.focusGlide = false;
      player.facing = 1;
      player.coyote = 0;
      player.jumpBuffer = 0;
      player.lastJump = false;
      player.won = false;
    }

    function getHumanControls() {
      return {
        left: keys.has("ArrowLeft") || keys.has("a"),
        right: keys.has("ArrowRight") || keys.has("d"),
        up: keys.has("ArrowUp") || keys.has("w"),
        down: keys.has("ArrowDown") || keys.has("s"),
        focus: keys.has("Shift"),
        jump: keys.has(" "),
      };
    }

    function rectsOverlap(a, b) {
      return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    function getSpikePeriod(spike) {
      return (spike.period || 140) * 1.32 * 0.9;
    }

    function getSpikeExtend(spike) {
      const period = getSpikePeriod(spike);
      const t = ((frame + spike.phase) % period) / period;
      if (t < 0.16) return t / 0.16;
      if (t < 0.35) return 1;
      if (t < 0.5) return 1 - (t - 0.35) / 0.15;
      return 0;
    }

    function getSpikeLength(spike) {
      return spike.length || 48;
    }

    function startNpcBubble() {
      const messages = npcStageMessages[Math.min(currentStage, npcStageMessages.length - 1)] || npcStageMessages[0];
      if (!messages.length) return;

      npcBubbleMessageIndex = (npcBubbleMessageIndex + 1) % messages.length;
      npcBubbleText = messages[npcBubbleMessageIndex];
      npcBubbleStartFrame = frame;
      npcBubbleNextFrame = frame + npcBubbleVisibleFrames + npcBubbleHiddenFrames;
    }

    function updateNpcBubble() {
      if (frame >= npcBubbleNextFrame) {
        startNpcBubble();
      }
    }

    function getNpcBubbleAlpha() {
      if (!npcBubbleText) return 0;

      const age = frame - npcBubbleStartFrame;
      if (age < 0 || age > npcBubbleVisibleFrames) return 0;

      return 1;
    }

    function startGameOver() {
      gameOver = true;
      gameOverFrame = 0;
      gameOverButtonRect = null;
      gameOverSpot = { x: player.x + player.w / 2, y: player.y + player.h };
      player.vx = 0;
      player.vy = 0;
      player.invuln = 0;
      player.hitStun = 0;
      statusText.textContent = "사망. 확인을 누르면 세이브 지점에서 부활합니다.";
    }

    function handlePlayerDeath(label = "피격") {
      if (gameOver || player.invuln > 0) return false;

      player.deaths += 1;
      statusText.textContent = `${label}. 세이브 지점에서 부활. 사망 ${player.deaths}회`;
      reset(true);
      player.invuln = 78;
      return true;
    }

    function applyDamage({ label = "피격" } = {}) {
      return handlePlayerDeath(label);
    }

    function applyFallDamage(dropDistance, landingSpeed, focusFrames = 0) {
      if (gameOver || dropDistance < 300 || landingSpeed < 7.8) return false;

      const focusReduction = Math.min(0.3, focusFrames / 120 * 0.3);
      if (focusReduction >= 0.3 && landingSpeed < 9.2) return false;

      return handlePlayerDeath("큰 낙하");
    }

    function splatDeath() {
      return handlePlayerDeath("치명적인 함정");
    }

    function confirmGameOver() {
      gameOver = false;
      gameOverFrame = 0;
      gameOverButtonRect = null;
      reset(true);
      player.invuln = 120;
      statusText.textContent = "부활 완료. 세이브 지점에서 재도전.";
    }

    function getCheckpointHealAmount() {
      const ratio = currentStage === hiddenStageIndex ? 0.08 : 0.15;
      return Math.ceil(player.maxHp * ratio);
    }

    function getCheckpointHealCooldownFrames() {
      return 600;
    }

    function getCheckpointKey(index) {
      return `${currentStage}:${index}`;
    }

    function update() {
      frame += 1;
      updateNpcBubble();

      if (gameOver) {
        gameOverFrame += 1;
        return;
      }

      if (player.won) {
        return;
      }

      player.focusGlide = false;
      player.invuln = Math.max(0, player.invuln - 1);
      player.hitStun = Math.max(0, player.hitStun - 1);

      const controls = getHumanControls();
      let { left, right, up, down, focus, jump } = controls;
      if (player.hitStun > 0) {
        left = false;
        right = false;
        up = false;
        down = false;
        focus = false;
        jump = false;
      }
      const jumpPressed = jump && !player.lastJump;
      player.crouching = down && player.grounded && !player.onRope && Math.abs(player.vx) < 1.2;
      player.lastJump = jump;
      if (jumpPressed || (up && !player.onRope)) {
        player.jumpBuffer = 8;
      } else {
        player.jumpBuffer = Math.max(0, player.jumpBuffer - 1);
      }

      if (left && !right) {
        player.facing = -1;
      } else if (right && !left) {
        player.facing = 1;
      }
      const playerBox = { x: player.x, y: player.y, w: player.w, h: player.h };
      const touchingRope = ropes.find((rope) => rectsOverlap(playerBox, { x: rope.x - 8, y: rope.y, w: 16, h: rope.h }));

      if (touchingRope && (up || down)) {
        player.onRope = true;
        player.x += (touchingRope.x - player.x - player.w / 2) * 0.22;
        player.vx = 0;
        player.vy = up ? -3.2 : down ? 3.2 : 0;
      }

      if (player.onRope) {
        player.fallStartY = null;
        player.fallFocusFrames = 0;
        if (!touchingRope) {
          player.onRope = false;
        } else {
          player.x += (touchingRope.x - player.x - player.w / 2) * 0.22;
          player.vx = left ? -1.4 : right ? 1.4 : 0;
          player.vy = up ? -3.45 : down ? 3.45 : 0;

          if (jumpPressed) {
            player.onRope = false;
            player.vy = -10.8;
            player.vx = left ? -4.9 : right ? 4.9 : player.facing * 3.1;
            player.jumpBuffer = 0;
          }
        }
      }

      if (!player.onRope) {
        const targetSpeed = (right ? 1 : 0) * 5.25 - (left ? 1 : 0) * 5.25;
        const accel = player.grounded ? 0.34 : 0.23;
        const friction = player.grounded ? 0.78 : 0.94;

        if (left || right) {
          player.vx += (targetSpeed - player.vx) * accel;
        } else {
          player.vx *= friction;
        }

        player.vx = Math.max(-5.6, Math.min(5.6, player.vx));

        if (player.grounded) {
          player.coyote = 7;
        } else {
          player.coyote = Math.max(0, player.coyote - 1);
        }

        if (player.jumpBuffer > 0 && player.coyote > 0) {
          player.vy = -11.9;
          player.grounded = false;
          player.coyote = 0;
          player.jumpBuffer = 0;
        }

        if (!jump && !up && player.vy < -4.2) {
          player.vy *= 0.82;
        }

        player.vy += player.vy < 0 ? 0.42 : 0.62;
        player.vy = Math.min(player.vy, 12.8);

        if (focus && player.vy > 0.6) {
          if (player.mp > 0) {
            player.mp = Math.max(0, player.mp - 18);
            player.vy = Math.min(player.vy, 3.75);
            player.fallFocusFrames += 1;
            player.focusGlide = true;
          } else if (frame - mpWarnFrame > 70) {
            mpWarnFrame = frame;
            statusText.textContent = "MP가 부족합니다.";
          }
        }
      }

      if (!player.onRope && !player.grounded && player.vy > 0 && player.fallStartY === null) {
        player.fallStartY = player.y;
        player.fallFocusFrames = 0;
      }

      player.x += player.vx;
      player.x = Math.max(0, Math.min(world.width - player.w, player.x));

      const beforeY = player.y;
      player.y += player.vy;
      const landingSpeed = player.vy;
      player.grounded = false;

      for (const p of platforms) {
        const surfaceY = platformSurfaceY(p);
        const horizontalOverlap = player.x < p.x + p.w && player.x + player.w > p.x;
        const crossedSurface = beforeY + player.h <= surfaceY + 6 && player.y + player.h >= surfaceY - 3;
        if (horizontalOverlap && crossedSurface && player.vy >= 0) {
          const fallDistance = player.fallStartY === null ? 0 : surfaceY - (player.fallStartY + player.h);
          const focusFrames = player.fallFocusFrames;
          player.y = surfaceY - player.h;
          player.vy = 0;
          player.grounded = true;
          player.fallStartY = null;
          player.fallFocusFrames = 0;
          player.coyote = 7;
          applyFallDamage(fallDistance, landingSpeed, focusFrames);
          if (gameOver) return;
        }
      }

      if (player.grounded && player.mp < player.maxMp) {
        player.mp = Math.min(player.maxMp, player.mp + 1.35);
      }

      for (const h of hazards) {
        h.x += h.dx || 0;
        h.y += h.dy || 0;
        if (h.min !== undefined && h.max !== undefined && (h.x < h.min || h.x > h.max)) h.dx *= -1;
        if (h.minY !== undefined && h.maxY !== undefined && (h.y < h.minY || h.y > h.maxY)) h.dy *= -1;
        const hitRadius = h.type === "star" ? h.r * 1.38 + 4 : h.r;
        const badBox = h.type === "necki"
          ? { x: h.x - h.w / 2, y: h.y - h.h / 2, w: h.w, h: h.h }
          : { x: h.x - hitRadius, y: h.y - hitRadius, w: hitRadius * 2, h: hitRadius * 2 };
        if (rectsOverlap(player, badBox)) {
          if (applyDamage({ respawn: false, sourceX: h.x, label: h.type === "necki" ? "몬스터 접촉" : "표창 피격" })) return;
        }
        if (gameOver) return;
      }

      for (const spike of spikes) {
        const extend = getSpikeExtend(spike);
        if (extend < 0.9) continue;

        const length = getSpikeLength(spike) * extend;
        let spikeBox = { x: spike.x, y: spike.y - length, w: spike.w, h: length };
        if (rectsOverlap(player, spikeBox)) {
          if (applyDamage({ respawn: false, sourceX: spike.x + spike.w / 2, label: "바닥창 피격" })) return;
        }
        if (gameOver) return;
      }

      for (let i = 0; i < checkpoints.length; i++) {
        const c = checkpoints[i];
        if (rectsOverlap(player, c)) {
          const checkpointKey = getCheckpointKey(i);
          player.checkpoint = { x: c.x - 10, y: Math.round(checkpointSurfaceY(c) - player.h) };
          const newlySaved = player.checkpointKey !== checkpointKey;
          player.checkpointKey = checkpointKey;

          const readyAt = checkpointHealReadyAt.get(checkpointKey) || 0;
          if (frame >= readyAt && player.mp < player.maxMp) {
            const mpRecoverAmount = Math.ceil(player.maxMp * 0.25);
            const beforeMp = player.mp;
            player.mp = Math.min(player.maxMp, player.mp + mpRecoverAmount);
            checkpointHealReadyAt.set(checkpointKey, frame + getCheckpointHealCooldownFrames());
            const mpRecovered = player.mp - beforeMp;
            statusText.textContent = `세이브 저장. MP ${mpRecovered} 회복.`;
          } else if (newlySaved) {
            statusText.textContent = player.mp >= player.maxMp
              ? "세이브 저장. MP는 가득 찼다."
              : "체크포인트 저장. 회복은 재충전 중.";
          }
        }
      }

      if (player.y > world.height - player.h - 6) {
        const floorSurface = world.height - 32 + platformGrassBottomOffset;
        const fallDistance = player.fallStartY === null ? 0 : floorSurface - (player.fallStartY + player.h);
        const focusFrames = player.fallFocusFrames;
        player.y = floorSurface - player.h;
        player.vy = 0;
        player.grounded = true;
        player.fallStartY = null;
        player.fallFocusFrames = 0;
        applyFallDamage(fallDistance, landingSpeed, focusFrames);
        if (gameOver) return;
      }

      if (rectsOverlap(player, stage.goal)) {
        player.won = true;
        clearTimer = 0;
        stageFinishElapsedMs = performance.now() - stageStartedAt;
        if (currentStage === visibleStageCount - 1 && stageFinishElapsedMs <= hiddenClearLimitMs) {
          hiddenUnlocked = true;
        }
        stageResults[currentStage] = {
          name: stage.name,
          deaths: player.deaths,
          elapsedMs: stageFinishElapsedMs,
        };
        statusText.textContent = `${stage.name} 성공. 사망 ${player.deaths}번.`;
      }
    }

    function drawBadLine(x1, y1, x2, y2, color, width = 2) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(Math.round(x1), Math.round(y1));
      ctx.lineTo(Math.round(x2), Math.round(y2));
      ctx.stroke();
    }

    function drawLeafCluster(x, y, scale, base, highlight) {
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(scale, scale);
      ctx.fillStyle = base;
      for (let i = 0; i < 9; i++) {
        const px = Math.cos(i * 1.9) * (18 + (i % 3) * 7);
        const py = Math.sin(i * 1.7) * (10 + (i % 4) * 4);
        ctx.beginPath();
        ctx.ellipse(px, py, 26 - (i % 2) * 5, 18 + (i % 3) * 3, i * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = highlight;
      for (let i = 0; i < 5; i++) {
        ctx.beginPath();
        ctx.ellipse(-22 + i * 12, -12 + (i % 2) * 8, 12, 7, -0.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    function drawLightRay(x, width, alpha) {
      const ray = ctx.createLinearGradient(x, 0, x + width, 0);
      ray.addColorStop(0, `rgba(255,255,220,0)`);
      ray.addColorStop(0.5, `rgba(255,255,220,${alpha})`);
      ray.addColorStop(1, `rgba(255,255,220,0)`);
      ctx.fillStyle = ray;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + width, 0);
      ctx.lineTo(x + width * 0.72, canvas.height);
      ctx.lineTo(x - width * 0.28, canvas.height);
      ctx.closePath();
      ctx.fill();
    }

    function drawSoftEllipse(x, y, w, h, color) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.ellipse(x, y, w, h, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    function drawCanopyBand(cameraY, depth, baseY, alpha) {
      const y = baseY - (cameraY * depth) % 240;
      for (let row = -1; row < 5; row++) {
        for (let i = 0; i < 11; i++) {
          const x = -80 + i * 108 + ((row + currentStage) % 2) * 38;
          const cy = y + row * 190 + (i % 3) * 18;
          drawLeafCluster(
            x,
            cy,
            1.05 + (i % 3) * 0.18,
            `rgba(27, 105, 47, ${alpha})`,
            `rgba(179, 229, 91, ${alpha * 0.45})`
          );
        }
      }
    }

    function drawTreeColumn(x, cameraY, width, palette, depth) {
      const parallaxY = -(cameraY * depth) % 620;
      const trunk = ctx.createLinearGradient(x, 0, x + width, 0);
      trunk.addColorStop(0, palette.dark);
      trunk.addColorStop(0.35, palette.mid);
      trunk.addColorStop(0.62, palette.light);
      trunk.addColorStop(1, palette.dark);

      for (let y = parallaxY - 680; y < canvas.height + 680; y += 620) {
        ctx.fillStyle = trunk;
        ctx.beginPath();
        ctx.moveTo(x + width * 0.18, y - 60);
        ctx.bezierCurveTo(x - width * 0.1, y + 190, x + width * 0.85, y + 310, x + width * 0.5, y + 640);
        ctx.lineTo(x + width, y + 650);
        ctx.bezierCurveTo(x + width * 0.65, y + 360, x + width * 1.15, y + 200, x + width * 0.62, y - 70);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = palette.line;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(x + width * 0.45, y);
        ctx.bezierCurveTo(x + width * 0.2, y + 160, x + width * 0.7, y + 310, x + width * 0.38, y + 560);
        ctx.stroke();

        ctx.strokeStyle = palette.vine;
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.moveTo(x + width * 0.8, y + 20);
        ctx.bezierCurveTo(x + width * 0.25, y + 130, x + width * 0.9, y + 280, x + width * 0.28, y + 480);
        ctx.stroke();

        ctx.strokeStyle = palette.glow || "rgba(204,255,157,0.16)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x + width * 0.54, y + 20);
        ctx.bezierCurveTo(x + width * 0.9, y + 170, x + width * 0.25, y + 350, x + width * 0.58, y + 590);
        ctx.stroke();
      }
    }

    function drawBackground(cameraY) {
      if (hasSuppliedBackground) {
        const imageRatio = backgroundImage.naturalWidth / backgroundImage.naturalHeight;
        const canvasRatio = canvas.width / canvas.height;
        let sx = 0;
        let sw = backgroundImage.naturalWidth;

        if (imageRatio > canvasRatio) {
          sw = backgroundImage.naturalHeight * canvasRatio;
          sx = (backgroundImage.naturalWidth - sw) / 2;
        }

        const visibleHeight = sw / canvasRatio;
        const maxScroll = Math.max(0, backgroundImage.naturalHeight - visibleHeight);
        const worldScrollable = Math.max(1, world.height - canvas.height);
        const scrollRatio = Math.max(0, Math.min(1, cameraY / worldScrollable));
        const sy = maxScroll * (0.14 + scrollRatio * 0.72);

        ctx.drawImage(backgroundImage, sx, sy, sw, visibleHeight, 0, 0, canvas.width, canvas.height);
        return;
      }

      const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
      gradient.addColorStop(0, "#eafdce");
      gradient.addColorStop(0.18, "#bde89d");
      gradient.addColorStop(0.52, stage.tint);
      gradient.addColorStop(1, "#245c39");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      drawSoftEllipse(540, 94, 430, 120, "rgba(255,255,218,0.25)");
      drawLightRay(80, 120, 0.42);
      drawLightRay(562, 160, 0.38);
      drawLightRay(742, 92, 0.25);

      drawCanopyBand(cameraY, 0.05, -40, 0.18);

      drawTreeColumn(-70, cameraY, 170, {
        dark: "rgba(44,92,33,0.45)",
        mid: "rgba(86,137,47,0.50)",
        light: "rgba(137,184,71,0.45)",
        line: "rgba(44,92,33,0.35)",
        vine: "rgba(27,111,38,0.35)",
        glow: "rgba(210,255,158,0.16)"
      }, 0.14);
      drawTreeColumn(105, cameraY, 210, {
        dark: "rgba(39,85,31,0.50)",
        mid: "rgba(91,142,50,0.55)",
        light: "rgba(151,190,76,0.50)",
        line: "rgba(32,82,31,0.38)",
        vine: "rgba(24,102,37,0.38)",
        glow: "rgba(216,255,165,0.18)"
      }, 0.2);
      drawTreeColumn(585, cameraY, 260, {
        dark: "rgba(38,83,33,0.48)",
        mid: "rgba(104,151,59,0.52)",
        light: "rgba(174,203,91,0.45)",
        line: "rgba(33,75,32,0.38)",
        vine: "rgba(20,97,36,0.36)",
        glow: "rgba(229,255,174,0.18)"
      }, 0.18);
      drawTreeColumn(810, cameraY, 190, {
        dark: "rgba(34,78,31,0.44)",
        mid: "rgba(88,134,48,0.50)",
        light: "rgba(138,184,76,0.42)",
        line: "rgba(31,70,32,0.36)",
        vine: "rgba(23,93,38,0.32)",
        glow: "rgba(219,255,168,0.14)"
      }, 0.16);

      drawCanopyBand(cameraY, 0.12, 30, 0.3);

      const leafOffset = -(cameraY * 0.1) % 160;
      for (let i = 0; i < 18; i++) {
        const x = (i * 91 + currentStage * 37) % 1040 - 40;
        const y = ((i * 59 + leafOffset) % 710) - 80;
        drawLeafCluster(
          x,
          y,
          0.75 + (i % 4) * 0.12,
          i % 2 ? "rgba(40,137,50,0.58)" : "rgba(68,159,58,0.52)",
          "rgba(184,231,102,0.36)"
        );
      }

      ctx.strokeStyle = "rgba(21,102,36,0.55)";
      ctx.lineWidth = 4;
      for (let i = 0; i < 20; i++) {
        const x = 15 + i * 54;
        const sway = Math.sin((i + currentStage) * 1.7) * 24;
        ctx.beginPath();
        ctx.moveTo(x, -40);
        ctx.bezierCurveTo(x + sway, 120, x - sway, 280, x + sway * 0.4, 620);
        ctx.stroke();
      }

      for (let i = 0; i < 42; i++) {
        const x = (i * 97 + currentStage * 41) % canvas.width;
        const y = (i * 53 + currentStage * 29 - cameraY * 0.04) % canvas.height;
        ctx.fillStyle = i % 2 ? "rgba(255,255,214,0.58)" : "rgba(178,255,135,0.48)";
        ctx.fillRect(x, y, 3 + (i % 3) * 2, 3 + (i % 2) * 2);
      }

      ctx.fillStyle = "rgba(47,99,40,0.16)";
      ctx.fillRect(0, canvas.height - 64, canvas.width, 64);

      const vignette = ctx.createRadialGradient(
        canvas.width * 0.55,
        canvas.height * 0.4,
        80,
        canvas.width * 0.55,
        canvas.height * 0.45,
        640
      );
      vignette.addColorStop(0, "rgba(255,255,255,0)");
      vignette.addColorStop(1, "rgba(5,24,14,0.34)");
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    function drawPlatform(p, cameraY, index) {
      const y = p.y - cameraY;
      ctx.fillStyle = "rgba(0, 0, 0, 0.24)";
      ctx.beginPath();
      ctx.ellipse(p.x + p.w / 2, y + 30, p.w * 0.46, 14, 0, 0, Math.PI * 2);
      ctx.fill();

      const logGradient = ctx.createLinearGradient(p.x, y - 8, p.x, y + 28);
      logGradient.addColorStop(0, "#be8741");
      logGradient.addColorStop(0.28, "#875528");
      logGradient.addColorStop(0.72, "#5a3418");
      logGradient.addColorStop(1, "#28180c");
      ctx.fillStyle = logGradient;
      ctx.fillRect(p.x, y - 2, p.w, p.h + 9);
      ctx.strokeStyle = "rgba(20, 12, 5, 0.92)";
      ctx.lineWidth = 2;
      ctx.strokeRect(p.x, y - 2, p.w, p.h + 9);

      ctx.fillStyle = "rgba(255, 220, 137, 0.18)";
      ctx.fillRect(p.x + 3, y, p.w - 6, 3);
      ctx.fillStyle = "rgba(24, 12, 5, 0.22)";
      ctx.fillRect(p.x + 3, y + p.h + 2, p.w - 6, 5);

      for (let x = p.x + 6; x < p.x + p.w; x += 27) {
        const ring = ctx.createRadialGradient(x - 4, y + 12, 3, x, y + 12, 18);
        ring.addColorStop(0, "#d7a45d");
        ring.addColorStop(0.42, "#a66f34");
        ring.addColorStop(1, "#553018");
        ctx.fillStyle = ring;
        ctx.beginPath();
        ctx.arc(x, y + 14, 17, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#241206";
        ctx.stroke();
        ctx.strokeStyle = "#5b3518";
        ctx.beginPath();
        ctx.arc(x - 2, y + 13, 9, 0, Math.PI * 1.85);
        ctx.stroke();
      }

      const moss = ctx.createLinearGradient(p.x, y - 12, p.x, y + 4);
      moss.addColorStop(0, "#91e860");
      moss.addColorStop(0.5, "#35a940");
      moss.addColorStop(1, "#167234");
      ctx.fillStyle = moss;
      ctx.beginPath();
      ctx.moveTo(p.x + 4, y - 7);
      for (let x = p.x + 8; x < p.x + p.w - 6; x += 12) {
        ctx.lineTo(x, y - 9 - ((x + index) % 3));
        ctx.lineTo(x + 6, y - 5);
      }
      ctx.lineTo(p.x + p.w - 4, y - 5);
      ctx.lineTo(p.x + p.w - 4, y + 1);
      ctx.lineTo(p.x + 4, y + 1);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = "#0f6c2a";
      if (index % 2 === 0) {
        ctx.beginPath();
        ctx.moveTo(p.x + 28, y + 16);
        ctx.lineTo(p.x + 46, y + 16);
        ctx.lineTo(p.x + 36, y + 54);
        ctx.closePath();
        ctx.fill();
      }
      if (index % 3 === 0) {
        ctx.beginPath();
        ctx.moveTo(p.x + p.w - 38, y + 16);
        ctx.lineTo(p.x + p.w - 21, y + 16);
        ctx.lineTo(p.x + p.w - 28, y + 58);
        ctx.closePath();
        ctx.fill();
      }

      ctx.strokeStyle = "#3c2411";
      ctx.lineWidth = 3;
      drawBadLine(p.x + 6, y - 8, p.x + 22, y - 18, "#4c2c13", 3);
      drawBadLine(p.x + p.w - 7, y - 7, p.x + p.w - 26, y - 17, "#4c2c13", 3);

      ctx.fillStyle = "#f7e783";
      ctx.fillRect(p.x + 5, y - 12, 7, 7);
      ctx.fillRect(p.x + p.w - 12, y - 12, 7, 7);
    }

    function drawHazard(h, cameraY) {
      const y = h.y - cameraY;
      if (h.type === "necki") {
        const direction = Math.sign(h.dx || 1);
        const wave = Math.sin(frame * 0.12 + h.x * 0.02);

        ctx.save();
        ctx.translate(h.x, y);
        ctx.scale(direction, 1);
        ctx.shadowColor = "rgba(6, 37, 25, 0.55)";
        ctx.shadowBlur = 7;

        const body = ctx.createLinearGradient(-28, -8, 28, 10);
        body.addColorStop(0, "#172a22");
        body.addColorStop(0.34, "#2d6f39");
        body.addColorStop(0.68, "#84c85d");
        body.addColorStop(1, "#183525");
        ctx.fillStyle = body;

        ctx.beginPath();
        ctx.ellipse(-16, wave * 2, 18, 9, -0.18, 0, Math.PI * 2);
        ctx.ellipse(3, -wave * 1.6, 20, 10, 0.12, 0, Math.PI * 2);
        ctx.ellipse(22, -2 + wave, 12, 9, 0.1, 0, Math.PI * 2);
        ctx.fill();

        ctx.shadowBlur = 0;
        ctx.strokeStyle = "#0b1712";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(-31, 4);
        ctx.bezierCurveTo(-14, -7 + wave, 7, 9 - wave, 31, -2);
        ctx.stroke();

        ctx.fillStyle = "#f6ffe2";
        ctx.fillRect(18, -8, 4, 4);
        ctx.fillRect(28, -7, 4, 4);
        ctx.fillStyle = "#07100c";
        ctx.fillRect(20, -7, 2, 2);
        ctx.fillRect(30, -6, 2, 2);

        ctx.restore();
        return;
      }

      if (h.type === "star") {
        ctx.save();
        ctx.translate(h.x, y);
        ctx.rotate(frame * 0.28 * Math.sign(h.dx || 1));

        if (hasStarImage) {
          const size = h.r * 4.4;
          ctx.imageSmoothingEnabled = false;
          ctx.shadowColor = "rgba(160, 230, 255, 0.55)";
          ctx.shadowBlur = 8;
          ctx.drawImage(starCanvas, -size / 2, -size / 2, size, size);
          ctx.shadowBlur = 0;
        } else {
          ctx.shadowColor = "rgba(165, 235, 255, 0.75)";
          ctx.shadowBlur = 10;

          ctx.fillStyle = "#dff9ff";
          ctx.strokeStyle = "#1d5d8f";
          ctx.lineWidth = 2.4;
          ctx.beginPath();
          for (let i = 0; i < 8; i++) {
            const angle = -Math.PI / 2 + i * Math.PI / 4;
            const radius = i % 2 === 0 ? h.r + 7 : h.r * 0.42;
            const px = Math.cos(angle) * radius;
            const py = Math.sin(angle) * radius;
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          }
          ctx.closePath();
          ctx.fill();
          ctx.stroke();

          ctx.shadowBlur = 0;
          ctx.fillStyle = "#5bd7ff";
          ctx.beginPath();
          ctx.arc(0, 0, h.r * 0.35, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(-h.r * 0.6, -h.r * 0.2);
          ctx.lineTo(h.r * 0.55, h.r * 0.15);
          ctx.stroke();
        }

        ctx.restore();
        return;
      }

      ctx.fillStyle = "#b55328";
      ctx.beginPath();
      ctx.arc(h.x, y, h.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#111";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.fillRect(h.x - 8, y - 6, 5, 5);
      ctx.fillRect(h.x + 3, y - 6, 5, 5);
      ctx.fillStyle = "#111";
      ctx.fillRect(h.x - 6, y - 4, 3, 3);
      ctx.fillRect(h.x + 5, y - 4, 3, 3);
      drawBadLine(h.x - 8, y + 7, h.x + 8, y + 10, "#111", 2);
    }

    function drawRope(rope, cameraY) {
      const y = rope.y - cameraY;
      ctx.strokeStyle = "#6b451d";
      ctx.lineWidth = 4;
      drawBadLine(rope.x, y, rope.x, y + rope.h, "#6b451d", 4);
      ctx.strokeStyle = "#b98b45";
      ctx.lineWidth = 2;
      for (let step = 8; step < rope.h; step += 18) {
        drawBadLine(rope.x - 7, y + step, rope.x + 7, y + step, "#b98b45", 2);
      }
    }

    function drawSpike(spike, cameraY) {
      const y = spike.y - cameraY;
      const extend = getSpikeExtend(spike);
      const length = getSpikeLength(spike) * Math.max(0.08, extend);
      const flash = extend > 0.72 ? 1 : 0.45;

      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      const count = Math.max(2, Math.floor(spike.w / 30));
      const slotY = y - 8;
      ctx.fillStyle = "#2b1b0e";
      ctx.fillRect(spike.x - 4, slotY - 4, spike.w + 8, 12);
      ctx.fillStyle = "#7a431f";
      ctx.fillRect(spike.x, slotY - 1, spike.w, 5);
      ctx.strokeStyle = "#1b1008";
      ctx.lineWidth = 2;
      ctx.strokeRect(spike.x - 4, slotY - 4, spike.w + 8, 12);

      for (let i = 0; i < count; i++) {
        const x = spike.x + 12 + i * ((spike.w - 24) / Math.max(1, count - 1));
        const dir = -1;
        const baseY = y;
        const tipY = baseY + dir * length;
        const shaftEndY = tipY - dir * 14;

        ctx.strokeStyle = `rgba(52, 31, 14, ${flash})`;
        drawBadLine(x, baseY, x, shaftEndY, ctx.strokeStyle, 6);

        ctx.strokeStyle = `rgba(178, 104, 36, ${flash})`;
        drawBadLine(x - 2, baseY + dir * 4, x - 2, shaftEndY, ctx.strokeStyle, 3);

        ctx.fillStyle = `rgba(218, 226, 218, ${flash})`;
        ctx.strokeStyle = "#263037";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, tipY);
        ctx.lineTo(x - 8, tipY - dir * 16);
        ctx.lineTo(x, tipY - dir * 10);
        ctx.lineTo(x + 8, tipY - dir * 16);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }

    function checkpointSurfaceY(c) {
      const centerX = c.x + c.w / 2;
      const surfaceHint = c.y + 1;
      const platform = platforms
        .filter((p) => centerX >= p.x - 10 && centerX <= p.x + p.w + 10)
        .sort((a, b) => Math.abs(platformSurfaceY(a) - surfaceHint) - Math.abs(platformSurfaceY(b) - surfaceHint))[0];

      return platform ? platformSurfaceY(platform) : surfaceHint;
    }

    function drawCheckpoint(c, cameraY, index = 0) {
      const baseY = checkpointSurfaceY(c);
      const x = c.x + c.w / 2;
      const bob = Math.sin(frame * 0.06 + index * 1.7) * 5;
      const y = baseY - cameraY - 34 + bob;
      const active = Math.abs(player.checkpoint.x - (c.x - 10)) < 1 && Math.abs(player.checkpoint.y - Math.round(baseY - player.h)) < 1;
      const checkpointKey = getCheckpointKey(index);
      const healReadyAt = checkpointHealReadyAt.get(checkpointKey) || 0;
      const healReady = frame >= healReadyAt;
      const cooldownRatio = healReady ? 1 : Math.max(0, Math.min(1, 1 - (healReadyAt - frame) / getCheckpointHealCooldownFrames()));
      const pulse = 0.78 + Math.sin(frame * 0.08 + x * 0.04) * 0.22;
      const glowAlpha = healReady ? (active ? 0.78 : 0.48) : 0.22;

      ctx.save();
      ctx.translate(Math.round(x), Math.round(y));
      ctx.imageSmoothingEnabled = false;

      ctx.fillStyle = "rgba(0, 0, 0, 0.24)";
      ctx.beginPath();
      ctx.ellipse(0, 36 - bob * 0.35, 18, 4, 0, 0, Math.PI * 2);
      ctx.fill();

      const glow = ctx.createRadialGradient(0, 0, 2, 0, 0, 32);
      glow.addColorStop(0, `rgba(255, 246, 222, ${glowAlpha})`);
      glow.addColorStop(0.45, `rgba(255, 71, 82, ${glowAlpha * 0.45})`);
      glow.addColorStop(1, "rgba(128, 28, 96, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(0, 0, 29 + pulse * 3, 0, Math.PI * 2);
      ctx.fill();

      if (active) {
        ctx.strokeStyle = "rgba(255, 249, 190, 0.86)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(0, 0, 26 + pulse * 2, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (hasElixirImage) {
        const potionW = 34;
        const potionH = 34;
        ctx.globalAlpha = healReady ? 1 : 0.55;
        ctx.drawImage(elixirCanvas, -potionW / 2, -potionH / 2, potionW, potionH);
        ctx.globalAlpha = 1;
      } else {
        ctx.save();
        ctx.rotate(-0.7);
        ctx.fillStyle = healReady ? "#d80f25" : "#77808a";
        ctx.strokeStyle = "#e8edf2";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(0, 4, 13, 10, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#d6dce3";
        ctx.fillRect(-5, -12, 8, 8);
        ctx.strokeStyle = "#4f5b67";
        ctx.strokeRect(-5, -12, 8, 8);
        ctx.restore();
      }

      if (!healReady) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.82)";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, 24, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * cooldownRatio);
        ctx.stroke();
      }

      ctx.fillStyle = "#fffdf0";
      for (let i = 0; i < 4; i++) {
        const angle = frame * 0.025 + i * Math.PI / 2;
        const sx = Math.cos(angle) * (22 + (i % 2) * 5);
        const sy = Math.sin(angle) * 15;
        ctx.fillRect(Math.round(sx), Math.round(sy), 3, 3);
      }

      ctx.restore();
    }

    function drawRewardPile(goal, cameraY) {
      if (currentStage !== 1 && currentStage !== 4) return;

      const x = goal.x + goal.w / 2;
      const y = goal.y - cameraY + goal.h + 10;
      const isHerbPile = currentStage === 4;

      ctx.save();
      ctx.translate(x, y);
      ctx.fillStyle = "rgba(12, 33, 17, 0.28)";
      ctx.beginPath();
      ctx.ellipse(0, 9, 52, 12, 0, 0, Math.PI * 2);
      ctx.fill();

      for (let i = 0; i < 16; i++) {
        const angle = i * 0.76;
        const stemX = Math.cos(angle) * (12 + (i % 4) * 5);
        const stemY = 8 - (i % 5) * 2;
        ctx.strokeStyle = isHerbPile ? "#237c32" : "#2f8f3f";
        ctx.lineWidth = 2;
        drawBadLine(stemX, stemY, stemX + Math.cos(angle) * 8, stemY - 18 - (i % 3) * 4, ctx.strokeStyle, 2);

        ctx.fillStyle = isHerbPile ? "#89e066" : (i % 2 === 0 ? "#ff82bd" : "#ffe07a");
        ctx.beginPath();
        ctx.ellipse(stemX + Math.cos(angle) * 9, stemY - 20 - (i % 3) * 4, 5 + (i % 2), 8, angle, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.fillStyle = isHerbPile ? "#5fc947" : "#ff6aaa";
      ctx.beginPath();
      ctx.ellipse(0, 2, 34, 13, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    function roundedRectPath(x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h - r);
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
    }

    function wrapText(text, maxWidth) {
      const words = text.split(" ");
      const lines = [];
      let line = "";

      for (const word of words) {
        const testLine = line ? `${line} ${word}` : word;
        if (ctx.measureText(testLine).width <= maxWidth || !line) {
          line = testLine;
        } else {
          lines.push(line);
          line = word;
        }
      }

      if (line) lines.push(line);
      return lines.slice(0, 3);
    }

    function drawNpcSpeechBubble(centerX, headY, text, alpha = 1) {
      if (!text || alpha <= 0) return;

      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.font = "bold 12px Arial";
      ctx.textBaseline = "middle";

      const maxTextWidth = 154;
      const lines = wrapText(text, maxTextWidth);
      const lineHeight = 15;
      const paddingX = 12;
      const paddingY = 9;
      const textWidth = Math.max(...lines.map((line) => ctx.measureText(line).width));
      const bubbleW = Math.round(Math.max(82, Math.min(188, textWidth + paddingX * 2)));
      const bubbleH = Math.round(lines.length * lineHeight + paddingY * 2);
      const x = Math.round(Math.max(8, Math.min(canvas.width - bubbleW - 8, centerX - bubbleW / 2)));
      const popOffset = Math.round((1 - alpha) * 5);
      const y = Math.round(Math.max(10, headY - bubbleH - 18 + popOffset));
      const tailX = Math.max(x + 20, Math.min(x + bubbleW - 20, centerX));

      ctx.fillStyle = "rgba(0, 0, 0, 0.24)";
      roundedRectPath(x + 2, y + 3, bubbleW, bubbleH, 8);
      ctx.fill();

      ctx.fillStyle = "rgba(250, 255, 247, 0.96)";
      roundedRectPath(x, y, bubbleW, bubbleH, 8);
      ctx.fill();

      ctx.strokeStyle = "#2f5f86";
      ctx.lineWidth = 2;
      roundedRectPath(x, y, bubbleW, bubbleH, 8);
      ctx.stroke();

      ctx.fillStyle = "rgba(250, 255, 247, 0.96)";
      ctx.beginPath();
      ctx.moveTo(tailX - 8, y + bubbleH - 1);
      ctx.lineTo(tailX + 8, y + bubbleH - 1);
      ctx.lineTo(tailX - 1, y + bubbleH + 11);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "#2f5f86";
      ctx.beginPath();
      ctx.moveTo(tailX - 8, y + bubbleH - 1);
      ctx.lineTo(tailX - 1, y + bubbleH + 11);
      ctx.lineTo(tailX + 8, y + bubbleH - 1);
      ctx.stroke();

      ctx.fillStyle = "#1f3142";
      ctx.textAlign = "center";
      lines.forEach((line, index) => {
        const textY = y + paddingY + lineHeight / 2 + index * lineHeight;
        ctx.fillText(line, x + bubbleW / 2, textY);
      });

      ctx.restore();
    }

    function getStartNpcCenterX(drawW) {
      const startPlatform = platforms[0];
      const startCenterX = stage.start.x + player.w / 2;
      const preferRight = stage.start.x < world.width / 2;
      let centerX = startCenterX + (preferRight ? 62 : -54);

      if (startPlatform) {
        const minX = startPlatform.x + drawW / 2 + 6;
        const maxX = startPlatform.x + startPlatform.w - drawW / 2 - 6;
        centerX = minX <= maxX
          ? Math.max(minX, Math.min(maxX, centerX))
          : startPlatform.x + startPlatform.w / 2;
      }

      return Math.max(drawW / 2 + 8, Math.min(world.width - drawW / 2 - 8, centerX));
    }

    function drawStartNpc(cameraY) {
      if (!hasNpcImage) return;

      const startPlatform = platforms[0];
      const npcScale = 1.08;
      const drawW = Math.round(npcSpriteBounds.w * npcScale);
      const drawH = Math.round(npcSpriteBounds.h * npcScale);
      const baseY = startPlatform ? platformSurfaceY(startPlatform) : stage.start.y + player.h;
      const centerX = getStartNpcCenterX(drawW);

      const x = Math.round(centerX - drawW / 2);
      const y = Math.round(baseY - drawH - cameraY);
      const screenBaseY = Math.round(baseY - cameraY);
      const bubbleAlpha = getNpcBubbleAlpha();

      ctx.save();
      ctx.imageSmoothingEnabled = false;
      drawNpcSpeechBubble(centerX, y + 8, npcBubbleText, bubbleAlpha);
      ctx.fillStyle = "rgba(0,0,0,0.22)";
      ctx.beginPath();
      ctx.ellipse(centerX, screenBaseY + 2, Math.max(14, drawW * 0.28), 4, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.drawImage(
        npcCanvas,
        npcSpriteBounds.x,
        npcSpriteBounds.y,
        npcSpriteBounds.w,
        npcSpriteBounds.h,
        x,
        y,
        drawW,
        drawH
      );
      ctx.restore();
    }

    function drawGoal(cameraY) {
      const goal = stage.goal;
      const centerX = goal.x + goal.w / 2;
      const centerY = goal.y - cameraY + goal.h / 2;
      const pulse = Math.sin(frame * 0.08) * 0.06 + 1;
      const size = Math.min(goal.w, goal.h) * 1.38 * pulse;

      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(frame * 0.01);

      ctx.globalAlpha = 0.32;
      ctx.fillStyle = "#4be9ff";
      ctx.beginPath();
      ctx.ellipse(0, 0, size * 0.58, size * 0.58, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      if (hasPortalImage) {
        ctx.rotate(-frame * 0.018);
        ctx.drawImage(portalImage, -size / 2, -size / 2, size, size);
      } else {
        for (let i = 0; i < 5; i++) {
          const radius = size * (0.26 + i * 0.055);
          const alpha = 0.78 - i * 0.12;
          const ring = ctx.createRadialGradient(0, 0, radius * 0.72, 0, 0, radius * 1.15);
          ring.addColorStop(0, `rgba(20, 84, 179, 0)`);
          ring.addColorStop(0.48, `rgba(72, 216, 255, ${alpha})`);
          ring.addColorStop(0.73, `rgba(18, 98, 230, ${alpha * 0.95})`);
          ring.addColorStop(1, `rgba(3, 24, 95, 0)`);

          ctx.rotate(0.42 + frame * 0.003);
          ctx.strokeStyle = ring;
          ctx.lineWidth = 10 - i;
          ctx.beginPath();
          ctx.arc(0, 0, radius, Math.PI * 0.1, Math.PI * 1.86);
          ctx.stroke();
        }

        for (let i = 0; i < 18; i++) {
          const angle = i * 0.74 + frame * 0.035;
          const radius = size * (0.32 + (i % 4) * 0.045);
          ctx.fillStyle = i % 3 === 0 ? "#ffffff" : "#5fefff";
          ctx.globalAlpha = 0.52 + (i % 3) * 0.12;
          ctx.fillRect(Math.cos(angle) * radius, Math.sin(angle) * radius, 4 + (i % 2) * 3, 2);
        }
        ctx.globalAlpha = 1;

        ctx.strokeStyle = "rgba(190, 246, 255, 0.92)";
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.arc(0, 0, size * 0.34, 0, Math.PI * 2);
        ctx.stroke();

        ctx.strokeStyle = "rgba(15, 70, 190, 0.9)";
        ctx.lineWidth = 9;
        ctx.beginPath();
        ctx.arc(0, 0, size * 0.46, Math.PI * 0.15, Math.PI * 1.75);
        ctx.stroke();
      }

      ctx.restore();
      drawRewardPile(goal, cameraY);
    }

    function drawLimb(x1, y1, x2, y2, width, color) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    function selectSpriteFrame() {
      if (player.onRope) {
        const frames = spriteAnimations.rope;
        return frames[Math.floor(frame / 8) % frames.length];
      }

      if (!player.grounded) {
        const frames = player.vy > 7 ? spriteAnimations.fall : spriteAnimations.jump;
        return frames[Math.floor(frame / 7) % frames.length];
      }

      if (player.crouching) {
        const frames = spriteAnimations.crouch;
        return frames[Math.floor(frame / 18) % frames.length];
      }

      if (Math.abs(player.vx) > 0.35) {
        const frames = spriteAnimations.run;
        return frames[Math.floor(frame / 7) % frames.length];
      }

      const frames = spriteAnimations.idle;
      return frames[0];
    }

    function getSpriteOpaqueBounds(sprite) {
      const key = `${sprite.sx}:${sprite.sy}:${sprite.sw}:${sprite.sh}`;
      if (spriteBoundsCache.has(key)) return spriteBoundsCache.get(key);

      let bounds = { x: 0, y: 0, w: sprite.sw, h: sprite.sh };
      if (hasCharacterSheet) {
        bounds = cleanSpriteCell(sprite);
      }

      spriteBoundsCache.set(key, bounds);
      return bounds;
    }

    function drawParachute(screenX, screenY) {
      const sway = Math.sin(frame * 0.12) * 2.5;
      const canopyX = Math.round(screenX + sway);
      const canopyY = Math.round(screenY - 98);

      ctx.save();
      ctx.imageSmoothingEnabled = false;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      ctx.strokeStyle = "rgba(45, 38, 38, 0.85)";
      ctx.lineWidth = 2;
      drawBadLine(canopyX - 26, canopyY + 22, screenX - 10, screenY - 35, ctx.strokeStyle, 2);
      drawBadLine(canopyX + 26, canopyY + 22, screenX + 10, screenY - 35, ctx.strokeStyle, 2);
      drawBadLine(canopyX - 8, canopyY + 26, screenX - 3, screenY - 34, ctx.strokeStyle, 1.5);
      drawBadLine(canopyX + 8, canopyY + 26, screenX + 3, screenY - 34, ctx.strokeStyle, 1.5);

      const canopy = ctx.createLinearGradient(canopyX, canopyY - 4, canopyX, canopyY + 28);
      canopy.addColorStop(0, "#fff2f7");
      canopy.addColorStop(0.28, "#ff8fb7");
      canopy.addColorStop(0.62, "#db2d73");
      canopy.addColorStop(1, "#7d1744");
      ctx.fillStyle = canopy;
      ctx.strokeStyle = "#3b2530";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(canopyX - 39, canopyY + 20);
      ctx.quadraticCurveTo(canopyX - 31, canopyY - 8, canopyX, canopyY - 13);
      ctx.quadraticCurveTo(canopyX + 31, canopyY - 8, canopyX + 39, canopyY + 20);
      ctx.lineTo(canopyX + 28, canopyY + 25);
      ctx.quadraticCurveTo(canopyX + 18, canopyY + 16, canopyX + 8, canopyY + 25);
      ctx.quadraticCurveTo(canopyX, canopyY + 16, canopyX - 8, canopyY + 25);
      ctx.quadraticCurveTo(canopyX - 18, canopyY + 16, canopyX - 28, canopyY + 25);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      ctx.strokeStyle = "rgba(255, 255, 255, 0.78)";
      ctx.lineWidth = 2;
      drawBadLine(canopyX - 25, canopyY + 14, canopyX - 6, canopyY - 7, ctx.strokeStyle, 2);
      drawBadLine(canopyX + 5, canopyY - 7, canopyX + 25, canopyY + 14, ctx.strokeStyle, 2);
      ctx.fillStyle = "rgba(255,255,255,0.72)";
      ctx.fillRect(canopyX - 13, canopyY - 6, 8, 4);

      ctx.restore();
    }

    function drawPlayer(cameraY) {
      const screenX = player.x + player.w / 2;
      const screenY = player.y - cameraY + player.h;
      const facing = player.facing;

      if (player.focusGlide) {
        drawParachute(screenX, screenY);
      }

      if (hasCharacterSheet) {
        const sprite = selectSpriteFrame();
        const spriteBounds = getSpriteOpaqueBounds(sprite);
        const characterScale = 0.7;
        const drawW = Math.round((player.crouching ? 112 : player.onRope ? 90 : 98) * characterScale);
        const drawH = Math.round((player.crouching ? 86 : player.onRope ? 116 : 122) * characterScale);
        const footY = ((spriteBounds.y + spriteBounds.h) / sprite.sh) * drawH;
        const drawX = Math.round(screenX - drawW / 2);
        const drawY = Math.round(screenY - footY);
        const scaleX = drawW / sprite.sw;
        const scaleY = drawH / sprite.sh;
        const croppedX = Math.round(drawX + spriteBounds.x * scaleX);
        const croppedY = Math.round(drawY + spriteBounds.y * scaleY);
        const croppedW = Math.round(spriteBounds.w * scaleX);
        const croppedH = Math.round(spriteBounds.h * scaleY);

        ctx.save();
        if (player.invuln > 0 && Math.floor(frame / 5) % 2 === 0) {
          ctx.globalAlpha = 0.42;
        }
        ctx.imageSmoothingEnabled = false;
        spriteFrameCanvas.width = sprite.sw;
        spriteFrameCanvas.height = sprite.sh;
        spriteFrameCtx.clearRect(0, 0, sprite.sw, sprite.sh);
        spriteFrameCtx.drawImage(characterCanvas, sprite.sx, sprite.sy, sprite.sw, sprite.sh, 0, 0, sprite.sw, sprite.sh);
        const framePixels = spriteFrameCtx.getImageData(0, 0, sprite.sw, sprite.sh);
        spriteFrameCtx.putImageData(makeSpriteSheetBackdropTransparent(framePixels), 0, 0);

        ctx.fillStyle = "rgba(0,0,0,0.26)";
        ctx.beginPath();
        ctx.ellipse(screenX, screenY + 2, 14, 3.5, 0, 0, Math.PI * 2);
        ctx.fill();

        if (facing > 0) {
          ctx.translate(drawX + drawW, drawY);
          ctx.scale(-1, 1);
          ctx.drawImage(
            spriteFrameCanvas,
            spriteBounds.x,
            spriteBounds.y,
            spriteBounds.w,
            spriteBounds.h,
            Math.round(spriteBounds.x * scaleX),
            Math.round(spriteBounds.y * scaleY),
            croppedW,
            croppedH
          );
        } else {
          ctx.drawImage(
            spriteFrameCanvas,
            spriteBounds.x,
            spriteBounds.y,
            spriteBounds.w,
            spriteBounds.h,
            croppedX,
            croppedY,
            croppedW,
            croppedH
          );
        }

        ctx.restore();
        return;
      }

      const runAmount = Math.min(1, Math.abs(player.vx) / 5);
      const walk = Math.sin(frame * 0.32) * runAmount;
      const airborne = !player.grounded && !player.onRope;
      const climb = player.onRope ? Math.sin(frame * 0.34) : 0;
      const bob = player.grounded ? Math.abs(Math.sin(frame * 0.32)) * runAmount * 2 : 0;

      ctx.save();
      if (player.invuln > 0 && Math.floor(frame / 5) % 2 === 0) {
        ctx.globalAlpha = 0.42;
      }
      ctx.translate(Math.round(screenX), Math.round(screenY - bob));
      ctx.scale(facing, 1);

      ctx.fillStyle = "rgba(0,0,0,0.28)";
      ctx.beginPath();
      ctx.ellipse(0, 5, player.crouching ? 30 : 24, player.crouching ? 6 : 7, 0, 0, Math.PI * 2);
      ctx.fill();

      if (hasCharacterSprite) {
        const targetHeight = 86;
        const targetWidth = Math.round(characterSpriteBounds.w * targetHeight / characterSpriteBounds.h);
        ctx.drawImage(
          characterCanvas,
          characterSpriteBounds.x,
          characterSpriteBounds.y,
          characterSpriteBounds.w,
          characterSpriteBounds.h,
          Math.round(-targetWidth / 2),
          -targetHeight - 2,
          targetWidth,
          targetHeight
        );

        if (airborne) {
          ctx.strokeStyle = "rgba(255,255,255,0.35)";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(-28, -30, 8, 0.2, Math.PI * 1.3);
          ctx.stroke();
        }

        ctx.restore();
        return;
      }

      const skin = "#ffd8a6";
      const skinDark = "#d99a66";
      const hair = "#1f1f24";
      const outfit = "#6fb8e8";
      const outfitDark = "#2b6f9b";
      const shoe = "#e5a13a";

      if (player.crouching) {
        ctx.translate(0, -4);
        drawLimb(-18, -18, -34, -8, 6, skin);
        drawLimb(18, -18, 34, -8, 6, skin);
        ctx.fillStyle = shoe;
        ctx.fillRect(-42, -7, 16, 6);
        ctx.fillRect(26, -7, 16, 6);
        ctx.fillStyle = outfitDark;
        ctx.fillRect(-24, -34, 48, 24);
        ctx.fillStyle = outfit;
        ctx.fillRect(-20, -38, 40, 18);
        ctx.fillStyle = skin;
        ctx.beginPath();
        ctx.ellipse(0, -52, 22, 19, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = skinDark;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = hair;
        ctx.beginPath();
        ctx.ellipse(-2, -64, 21, 11, -0.15, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        return;
      }

      const armSwing = player.onRope ? climb * 8 : walk * 10;
      const legSwing = airborne ? 0.5 : walk;

      drawLimb(-8, -42, -18, -24 + armSwing, 6, skin);
      drawLimb(8, -42, 18, -24 - armSwing, 6, skin);
      drawLimb(-7, -18, -13, -2 + legSwing * 8, 7, skin);
      drawLimb(7, -18, 13, -2 - legSwing * 8, 7, skin);

      ctx.fillStyle = shoe;
      ctx.fillRect(-19, -3 + legSwing * 8, 16, 6);
      ctx.fillRect(5, -3 - legSwing * 8, 16, 6);

      ctx.fillStyle = outfitDark;
      ctx.fillRect(-12, -45, 24, 28);
      ctx.fillStyle = outfit;
      ctx.fillRect(-10, -48, 20, 20);
      ctx.fillStyle = "#eef9ff";
      ctx.fillRect(-5, -48, 4, 18);
      ctx.fillRect(3, -48, 4, 18);

      ctx.fillStyle = skin;
      ctx.beginPath();
      ctx.ellipse(0, -67, 22, 21, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = skinDark;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = hair;
      ctx.beginPath();
      ctx.ellipse(-5, -80, 18, 11, -0.35, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(-22, -74, 15, 12);
      ctx.beginPath();
      ctx.ellipse(16, -83, 16, 10, 0.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(17, -90, 16, 10);

      ctx.fillStyle = "#ffffff";
      ctx.fillRect(-14, -68, 8, 7);
      ctx.fillRect(6, -68, 8, 7);
      ctx.fillStyle = "#254c7d";
      ctx.fillRect(-12, -67, 4, 5);
      ctx.fillRect(8, -67, 4, 5);
      ctx.fillStyle = "#1b1512";
      ctx.fillRect(-13, -75, 10, 3);
      ctx.fillRect(4, -75, 11, 3);

      ctx.fillStyle = "#b85e5e";
      ctx.fillRect(-4, -55, 8, 2);

      if (airborne) {
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(-28, -30, 8, 0.2, Math.PI * 1.3);
        ctx.stroke();
      }

      ctx.restore();
    }

    function drawMiniMap(cameraY) {
      const x = 8;
      const y = 8;
      const w = 238;
      const h = 284;
      const headerH = 76;

      ctx.save();
      ctx.globalAlpha = 0.78;
      const header = ctx.createLinearGradient(x, y, x, y + headerH);
      header.addColorStop(0, "rgba(235, 238, 224, 0.5)");
      header.addColorStop(0.25, "rgba(108, 112, 116, 0.52)");
      header.addColorStop(0.58, "rgba(31, 34, 38, 0.62)");
      header.addColorStop(1, "rgba(16, 18, 20, 0.7)");
      ctx.fillStyle = header;
      ctx.fillRect(x, y, w, headerH);

      const mapBg = ctx.createLinearGradient(x, y + headerH, x, y + h);
      mapBg.addColorStop(0, "rgba(211, 224, 218, 0.58)");
      mapBg.addColorStop(0.48, "rgba(181, 192, 180, 0.6)");
      mapBg.addColorStop(1, "rgba(236, 238, 229, 0.64)");
      ctx.fillStyle = mapBg;
      ctx.fillRect(x, y + headerH, w, h - headerH);

      ctx.globalAlpha = 0.82;
      ctx.fillStyle = "rgba(255,255,255,0.18)";
      ctx.fillRect(x, y, w, 3);
      ctx.strokeStyle = "rgba(242, 245, 238, 0.66)";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
      ctx.strokeStyle = "rgba(39, 50, 57, 0.72)";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 4, y + 4, w - 8, h - 8);
      ctx.strokeStyle = "rgba(8, 14, 18, 0.5)";
      ctx.beginPath();
      ctx.moveTo(x + 4, y + headerH);
      ctx.lineTo(x + w - 4, y + headerH);
      ctx.stroke();

      ctx.globalAlpha = 0.9;
      const iconX = x + 9;
      const iconY = y + 16;
      const iconSize = 42;
      ctx.fillStyle = "rgba(245, 248, 242, 0.68)";
      ctx.fillRect(iconX, iconY, iconSize, iconSize);
      ctx.strokeStyle = "#d7e2d6";
      ctx.lineWidth = 2;
      ctx.strokeRect(iconX, iconY, iconSize, iconSize);
      if (hasElliniaEmblem) {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(elliniaEmblemImage, iconX + 4, iconY + 4, iconSize - 8, iconSize - 8);
      } else {
        const iconGrad = ctx.createLinearGradient(iconX, iconY, iconX + iconSize, iconY + iconSize);
        iconGrad.addColorStop(0, "#5fd7ff");
        iconGrad.addColorStop(0.45, "#f4e063");
        iconGrad.addColorStop(1, "#c14b43");
        ctx.fillStyle = iconGrad;
        ctx.beginPath();
        ctx.moveTo(iconX + 21, iconY + 5);
        ctx.bezierCurveTo(iconX + 36, iconY + 11, iconX + 35, iconY + 34, iconX + 21, iconY + 38);
        ctx.bezierCurveTo(iconX + 7, iconY + 34, iconX + 6, iconY + 11, iconX + 21, iconY + 5);
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      ctx.globalAlpha = 1;
      ctx.fillStyle = "#f7f7f2";
      ctx.strokeStyle = "rgba(0,0,0,0.72)";
      ctx.lineWidth = 3;
      ctx.font = "bold 17px Arial";
      const stageTitle = stage.hidden ? "극한의 숲" : `인내의 숲 ${currentStage + 1}`;
      const stageSubTitle = stage.hidden ? "숨겨진 길" : stage.name.replace(/^인내의 숲 /, "");
      ctx.strokeText(stageTitle, x + 62, y + 31);
      ctx.fillText(stageTitle, x + 62, y + 31);
      ctx.font = "bold 14px Arial";
      ctx.strokeText(stageSubTitle, x + 62, y + 54);
      ctx.fillText(stageSubTitle, x + 62, y + 54);

      ctx.fillStyle = "rgba(48, 35, 24, 0.5)";
      ctx.fillRect(x + 8, y + headerH + 8, w - 16, 24);
      ctx.fillStyle = "#d6d2ca";
      ctx.font = "bold 13px Arial";
      ctx.fillText(stage.hidden ? "Hidden Challenge" : "Forest Route", x + 44, y + headerH + 25);

      const mapX = x + 14;
      const mapY = y + headerH + 42;
      const mapW = w - 28;
      const mapH = h - headerH - 70;

      ctx.save();
      ctx.globalAlpha = 0.86;
      ctx.beginPath();
      ctx.rect(mapX, mapY, mapW, mapH);
      ctx.clip();

      ctx.fillStyle = "rgba(95, 108, 105, 0.26)";
      for (let i = 0; i < 18; i++) {
        const stoneX = mapX + 8 + (i * 43) % mapW;
        const stoneY = mapY + 4 + (i * 17) % mapH;
        ctx.beginPath();
        ctx.ellipse(stoneX, stoneY, 14 + (i % 3) * 4, 7 + (i % 2) * 2, 0.2, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.strokeStyle = "rgba(89, 102, 103, 0.64)";
      ctx.lineWidth = 1;
      for (let gx = mapX; gx <= mapX + mapW; gx += 24) {
        ctx.beginPath();
        ctx.moveTo(gx, mapY);
        ctx.lineTo(gx, mapY + mapH);
        ctx.stroke();
      }
      for (let gy = mapY; gy <= mapY + mapH; gy += 18) {
        ctx.beginPath();
        ctx.moveTo(mapX, gy);
        ctx.lineTo(mapX + mapW, gy);
        ctx.stroke();
      }

      let boundsMinX = 0;
      let boundsMaxX = world.width;
      let boundsMinY = stage.goal.y;
      let boundsMaxY = world.height;

      for (const p of platforms) {
        boundsMinX = Math.min(boundsMinX, p.x);
        boundsMaxX = Math.max(boundsMaxX, p.x + p.w);
        boundsMinY = Math.min(boundsMinY, p.y - 60);
        boundsMaxY = Math.max(boundsMaxY, p.y + 60);
      }
      for (const h of hazards) {
        boundsMinX = Math.min(boundsMinX, h.min ?? h.x - h.r);
        boundsMaxX = Math.max(boundsMaxX, h.max ?? h.x + h.r);
        boundsMinY = Math.min(boundsMinY, h.minY ?? h.y - h.r);
        boundsMaxY = Math.max(boundsMaxY, h.maxY ?? h.y + h.r);
      }

      boundsMinX = Math.max(0, boundsMinX - 24);
      boundsMaxX = Math.min(world.width, boundsMaxX + 24);
      boundsMinY = Math.max(0, boundsMinY - 34);
      boundsMaxY = Math.min(world.height, boundsMaxY + 34);

      const boundsW = Math.max(1, boundsMaxX - boundsMinX);
      const boundsH = Math.max(1, boundsMaxY - boundsMinY);
      const mapScale = Math.min(mapW / boundsW, mapH / boundsH);
      const contentW = boundsW * mapScale;
      const contentH = boundsH * mapScale;
      const contentX = mapX + (mapW - contentW) / 2;
      const contentY = mapY + (mapH - contentH) / 2;

      ctx.strokeStyle = "rgba(37, 47, 48, 0.72)";
      ctx.lineWidth = 1;
      ctx.strokeRect(contentX, contentY, contentW, contentH);

      function miniX(worldX) {
        return contentX + (worldX - boundsMinX) * mapScale;
      }

      function miniY(worldY) {
        return contentY + (worldY - boundsMinY) * mapScale;
      }

      const viewTop = cameraY;
      const viewBottom = cameraY + canvas.height - classicHudHeight;
      const viewY = miniY(viewTop);
      const viewH = Math.max(4, miniY(viewBottom) - miniY(viewTop));
      ctx.fillStyle = "rgba(88, 169, 255, 0.14)";
      ctx.fillRect(mapX, viewY, mapW, viewH);
      ctx.strokeStyle = "rgba(58, 142, 255, 0.58)";
      ctx.strokeRect(mapX + 1, viewY, mapW - 2, viewH);

      for (const p of platforms) {
        const px = miniX(p.x);
        const py = miniY(platformSurfaceY(p));
        const pw = Math.max(4, p.w * mapScale);
        ctx.fillStyle = "#6b3d17";
        ctx.fillRect(px, py, pw, 3);
        ctx.fillStyle = "#1bd958";
        ctx.fillRect(px, py - 3, pw, 3);
        ctx.fillStyle = "rgba(255, 240, 120, 0.88)";
        ctx.fillRect(px + 1, py - 4, Math.min(4, pw), 1);
      }

      for (const spike of spikes) {
        const sx = miniX(spike.x + spike.w / 2);
        const sy = miniY(spike.y);
        ctx.fillStyle = "#dc3030";
        ctx.beginPath();
        ctx.moveTo(sx, sy - 8);
        ctx.lineTo(sx - 5, sy + 2);
        ctx.lineTo(sx + 5, sy + 2);
        ctx.closePath();
        ctx.fill();
      }

      for (const h of hazards) {
        const hx = miniX(h.x);
        const hy = miniY(h.y);
        ctx.strokeStyle = "rgba(59, 128, 255, 0.55)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (h.min !== undefined && h.max !== undefined) {
          ctx.moveTo(miniX(h.min), hy);
          ctx.lineTo(miniX(h.max), hy);
        } else if (h.minY !== undefined && h.maxY !== undefined) {
          ctx.moveTo(hx, miniY(h.minY));
          ctx.lineTo(hx, miniY(h.maxY));
        }
        ctx.stroke();
        ctx.fillStyle = h.dy ? "#29c9ff" : "#ff46dc";
        ctx.beginPath();
        ctx.arc(hx, hy, Math.max(3, h.r * 0.32), 0, Math.PI * 2);
        ctx.fill();
      }

      for (const c of checkpoints) {
        const cx = miniX(c.x + c.w / 2);
        const cy = miniY(checkpointSurfaceY(c));
        ctx.fillStyle = "#30e85a";
        ctx.fillRect(cx - 2, cy - 10, 5, 11);
        ctx.fillStyle = "#fff265";
        ctx.fillRect(cx + 2, cy - 10, 8, 5);
      }

      const goalX = miniX(stage.goal.x + stage.goal.w / 2);
      const goalY = miniY(stage.goal.y + stage.goal.h / 2);
      ctx.fillStyle = "#24d7ff";
      ctx.beginPath();
      ctx.arc(goalX, goalY, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();

      const playerDotX = miniX(player.x + player.w / 2);
      const playerDotY = miniY(player.y + player.h / 2);
      ctx.fillStyle = "#ff32e6";
      ctx.fillRect(playerDotX - 3, playerDotY - 8, 6, 12);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(playerDotX - 1, playerDotY - 6, 2, 3);
      ctx.restore();

      ctx.globalAlpha = 0.72;
      ctx.fillStyle = "rgba(241, 244, 237, 0.55)";
      ctx.fillRect(x + 5, y + h - 24, w - 10, 19);
      ctx.strokeStyle = "rgba(150, 158, 150, 0.62)";
      ctx.lineWidth = 1;
      for (let gx = x + 8; gx < x + w - 8; gx += 11) {
        ctx.beginPath();
        ctx.moveTo(gx, y + h - 24);
        ctx.lineTo(gx, y + h - 6);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;
      ctx.fillStyle = "#273137";
      ctx.font = "bold 11px Arial";
      ctx.fillText("P", playerDotX + 5, playerDotY - 4);
      ctx.fillStyle = "#0e8d25";
      ctx.fillText("SAVE", x + w - 58, y + h - 10);
      ctx.restore();
    }

    function getElapsedParts() {
      const elapsedMs = stageFinishElapsedMs ?? (performance.now() - stageStartedAt);
      const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
      return {
        minutes: Math.floor(totalSeconds / 60),
        seconds: totalSeconds % 60,
      };
    }

    function formatElapsedMs(elapsedMs) {
      const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      return `${minutes}분 ${String(seconds).padStart(2, "0")}초`;
    }

    function drawMapleTimePanel() {
      const { minutes, seconds } = getElapsedParts();
      const x = Math.round(canvas.width / 2 - 154);
      const y = 10;
      const w = 308;
      const h = 54;

      const panel = ctx.createLinearGradient(x, y, x, y + h);
      panel.addColorStop(0, "rgba(84, 63, 20, 0.94)");
      panel.addColorStop(0.48, "rgba(48, 32, 10, 0.96)");
      panel.addColorStop(1, "rgba(31, 20, 7, 0.98)");
      ctx.fillStyle = panel;
      ctx.fillRect(x, y, w, h);

      ctx.strokeStyle = "#f3d36b";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
      ctx.strokeStyle = "rgba(30, 17, 4, 0.9)";
      ctx.lineWidth = 3;
      ctx.strokeRect(x + 4, y + 4, w - 8, h - 8);

      ctx.fillStyle = "#e7d989";
      ctx.font = "bold 13px Arial";
      ctx.fillText("소요시간", x + 26, y + 22);
      ctx.beginPath();
      ctx.fillStyle = "#f6dc62";
      ctx.arc(x + 14, y + 17, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#3a2608";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      drawBadLine(x + 14, y + 17, x + 14, y + 13, "#3a2608", 1.5);
      drawBadLine(x + 14, y + 17, x + 18, y + 17, "#3a2608", 1.5);

      const minuteText = String(minutes).padStart(2, "0");
      const secondText = String(seconds).padStart(2, "0");
      ctx.textAlign = "right";
      ctx.shadowColor = "rgba(255, 246, 174, 0.7)";
      ctx.shadowBlur = 7;
      ctx.fillStyle = "#fff7b8";
      ctx.font = "bold 38px Consolas, 'Courier New', monospace";
      ctx.fillText(minuteText, x + 164, y + 44);
      ctx.fillText(secondText, x + 268, y + 44);
      ctx.shadowBlur = 0;

      ctx.textAlign = "left";
      ctx.fillStyle = "#fff0a0";
      ctx.font = "bold 15px Arial";
      ctx.fillText("분", x + 172, y + 42);
      ctx.fillText("초", x + 276, y + 42);
    }

    function drawStatusBar(x, y, w, label, valueText, fill, bg = "#14181f") {
      ctx.fillStyle = "#e3edf5";
      ctx.font = "bold 12px Arial";
      ctx.fillText(label, x, y + 11);

      const labelW = label.length > 3 ? 40 : label === "EXP" ? 31 : 28;
      const barX = x + labelW;
      const barY = y + 1;
      const barW = w - labelW;
      const barH = 15;
      ctx.fillStyle = "#0b1016";
      ctx.fillRect(barX - 2, barY - 2, barW + 4, barH + 4);
      ctx.strokeStyle = "rgba(230, 238, 244, 0.72)";
      ctx.strokeRect(barX - 1, barY - 1, barW + 2, barH + 2);
      ctx.fillStyle = bg;
      ctx.fillRect(barX, barY, barW, barH);

      const fillW = Math.max(0, Math.min(barW, fill.ratio * barW));
      const fillGrad = ctx.createLinearGradient(barX, barY, barX, barY + barH);
      fillGrad.addColorStop(0, fill.light);
      fillGrad.addColorStop(0.55, fill.mid);
      fillGrad.addColorStop(1, fill.dark);
      ctx.fillStyle = fillGrad;
      ctx.fillRect(barX, barY, fillW, barH);
      ctx.fillStyle = "rgba(255,255,255,0.42)";
      ctx.fillRect(barX + 1, barY + 1, Math.max(0, fillW - 2), 3);

      ctx.fillStyle = "#f8fbff";
      ctx.font = "10px Arial";
      ctx.textAlign = "right";
      ctx.fillText(valueText, barX + barW - 4, y + 12);
      ctx.textAlign = "left";
    }

    function drawHudPanel(x, y, w, h, alpha = 1) {
      const grad = ctx.createLinearGradient(x, y, x, y + h);
      grad.addColorStop(0, `rgba(112, 124, 133, ${0.95 * alpha})`);
      grad.addColorStop(0.5, `rgba(48, 58, 68, ${0.98 * alpha})`);
      grad.addColorStop(1, `rgba(22, 29, 38, ${alpha})`);
      ctx.fillStyle = grad;
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = `rgba(222, 234, 242, ${0.75 * alpha})`;
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      ctx.fillStyle = `rgba(255,255,255,${0.18 * alpha})`;
      ctx.fillRect(x + 1, y + 1, w - 2, 2);
    }

    function drawClassicMapleHud() {
      const h = classicHudHeight;
      const y = canvas.height - h;
      const utilityH = 31;
      const mainY = y + utilityH;
      const mainH = h - utilityH;

      ctx.save();
      ctx.fillStyle = "#111820";
      ctx.fillRect(0, y, canvas.width, h);

      const strip = ctx.createLinearGradient(0, y, 0, y + utilityH);
      strip.addColorStop(0, "rgba(228, 218, 230, 0.82)");
      strip.addColorStop(0.34, "rgba(148, 157, 166, 0.92)");
      strip.addColorStop(1, "rgba(58, 66, 75, 0.98)");
      ctx.fillStyle = strip;
      ctx.fillRect(0, y, canvas.width, utilityH);
      ctx.strokeStyle = "rgba(255,255,255,0.72)";
      ctx.beginPath();
      ctx.moveTo(0, y + 1.5);
      ctx.lineTo(canvas.width, y + 1.5);
      ctx.stroke();
      ctx.strokeStyle = "rgba(26, 31, 39, 0.9)";
      ctx.beginPath();
      ctx.moveTo(0, y + utilityH - 1);
      ctx.lineTo(canvas.width, y + utilityH - 1);
      ctx.stroke();

      drawHudPanel(0, mainY, 94, mainH);
      ctx.fillStyle = "#f3f6f7";
      ctx.font = "bold 22px Arial";
      ctx.fillText("LV.", 6, mainY + 39);
      const level = String(currentStage + 1);
      ctx.fillStyle = "#eb8429";
      ctx.fillRect(48, mainY + 23, 30, 19);
      ctx.fillStyle = "#fff6df";
      ctx.font = "bold 14px Arial";
      ctx.fillText(level, 52, mainY + 38);

      drawHudPanel(94, mainY, 158, mainH, 0.96);
      ctx.fillStyle = "rgba(15, 20, 27, 0.72)";
      ctx.fillRect(100, mainY + 12, 145, 34);
      ctx.fillStyle = "#dfe8ed";
      ctx.font = "bold 13px Arial";
      ctx.fillText(stage.hidden ? "Hidden Challenge" : "토벤머리 용사", 108, mainY + 34);

      const ascentRatio = Math.max(0, Math.min(1, 1 - player.y / world.height));
      drawHudPanel(252, mainY, 440, mainH, 0.98);
      drawStatusBar(263, mainY + 8, 128, "DEAD", `${player.deaths}회`, {
        ratio: 1,
        light: "#fff07a",
        mid: "#ef9f22",
        dark: "#9b4e05",
      });
      drawStatusBar(405, mainY + 8, 128, "MP", `${Math.round(player.mp)}/${player.maxMp}`, {
        ratio: player.mp / player.maxMp,
        light: "#88dcff",
        mid: "#1688df",
        dark: "#064b9a",
      });
      drawStatusBar(547, mainY + 8, 134, "EXP", `HEIGHT ${Math.round(ascentRatio * 100)}%`, {
        ratio: ascentRatio,
        light: "#f4ff6a",
        mid: "#93d423",
        dark: "#3d7b0f",
      });
      ctx.fillStyle = "#d7e3ec";
      ctx.font = "11px Arial";
      ctx.fillText(`Stage ${currentStage + 1}/${currentStage === hiddenStageIndex ? stages.length : visibleStageCount}`, 264, mainY + 50);
      ctx.fillText(`Death ${player.deaths}`, 348, mainY + 50);

      drawHudPanel(696, mainY, 94, mainH, 0.96);
      ctx.fillStyle = "#eef4f7";
      ctx.font = "bold 12px Arial";
      ctx.fillText("STATUS", 718, mainY + 19);
      ctx.fillStyle = "#ffcf62";
      ctx.font = "bold 22px Arial";
      ctx.fillText(`${player.deaths}`, 733, mainY + 43);

      function mapleButton(bx, by, bw, bh, label, color1, color2, fontSize = 10) {
        const grad = ctx.createLinearGradient(bx, by, bx, by + bh);
        grad.addColorStop(0, color1);
        grad.addColorStop(1, color2);
        ctx.fillStyle = grad;
        ctx.fillRect(bx, by, bw, bh);
        ctx.strokeStyle = "rgba(232, 244, 255, 0.9)";
        ctx.lineWidth = 1.3;
        ctx.strokeRect(bx + 1, by + 1, bw - 2, bh - 2);
        ctx.fillStyle = "rgba(0,0,0,0.22)";
        ctx.fillRect(bx + 3, by + bh - 8, bw - 6, 4);
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${fontSize}px Arial`;
        ctx.textAlign = "center";
        ctx.fillText(label, bx + bw / 2, by + bh - 9);
        ctx.textAlign = "left";
      }

      mapleButton(660, y + 5, 72, 20, "KEY SETTING", "#42b9ee", "#126aa5", 9);
      mapleButton(736, y + 5, 74, 20, "QUICK SLOT", "#35a6e1", "#0a609e", 9);
      mapleButton(806, mainY + 8, 72, 45, "CASHSHOP", "#f33f52", "#9d1026", 10);
      mapleButton(882, mainY + 8, 60, 45, "MENU", "#208edd", "#075994", 10);

      const chatX = 16;
      const chatY = y + 5;
      const chatW = 630;
      const chatH = 20;
      ctx.fillStyle = "rgba(225, 230, 236, 0.58)";
      ctx.fillRect(chatX, chatY, chatW, chatH);
      ctx.strokeStyle = "rgba(255,255,255,0.48)";
      ctx.strokeRect(chatX + 0.5, chatY + 0.5, chatW - 1, chatH - 1);
      ctx.fillStyle = "rgba(35, 43, 52, 0.86)";
      ctx.font = "bold 12px Arial";
      const message = statusText.textContent || "대충 시작!";
      ctx.save();
      ctx.beginPath();
      ctx.rect(chatX + 8, chatY + 2, chatW - 16, chatH - 4);
      ctx.clip();
      ctx.fillText(message, chatX + 10, chatY + 15);
      ctx.restore();
      ctx.restore();
    }

    function drawDummyBuffs() {
      const slot = 34;
      const gap = 3;
      const x = canvas.width - slot * 2 - gap - 14;
      const y = 16;
      ctx.save();

      function drawSlot(bx, by) {
        ctx.fillStyle = "rgba(10, 18, 18, 0.35)";
        ctx.fillRect(bx + 2, by + 3, slot, slot);
        const bg = ctx.createLinearGradient(bx, by, bx, by + slot);
        bg.addColorStop(0, "#d4e4dc");
        bg.addColorStop(0.5, "#95aaa0");
        bg.addColorStop(1, "#5f746e");
        ctx.fillStyle = bg;
        ctx.fillRect(bx, by, slot, slot);
        ctx.strokeStyle = "#1b2a2a";
        ctx.lineWidth = 2;
        ctx.strokeRect(bx + 1, by + 1, slot - 2, slot - 2);
        ctx.fillStyle = "rgba(255,255,255,0.42)";
        ctx.fillRect(bx + 4, by + 4, slot - 8, 4);
        ctx.fillStyle = "rgba(18, 32, 31, 0.26)";
        ctx.fillRect(bx + 5, by + slot - 8, slot - 10, 4);
      }

      function drawWingBuff(bx, by) {
        ctx.save();
        ctx.translate(bx + 17, by + 17);
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#283334";
        ctx.fillStyle = "#e7eeee";
        ctx.beginPath();
        ctx.moveTo(-3, 0);
        ctx.lineTo(-14, -8);
        ctx.lineTo(-12, 5);
        ctx.lineTo(-3, 10);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(3, 0);
        ctx.lineTo(14, -8);
        ctx.lineTo(12, 5);
        ctx.lineTo(3, 10);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#f9ffff";
        ctx.fillRect(-11, -5, 5, 4);
        ctx.fillRect(6, -5, 5, 4);
        ctx.strokeStyle = "#283334";
        drawBadLine(0, -8, 0, 10, "#283334", 3);
        drawBadLine(-7, 6, 7, 6, "#283334", 2);
        ctx.restore();
      }

      function drawBootBuff(bx, by) {
        ctx.save();
        ctx.translate(bx + 18, by + 17);
        ctx.rotate(-0.35);
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.fillStyle = "#d9e3df";
        ctx.strokeStyle = "#273232";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(-4, -13);
        ctx.lineTo(9, -13);
        ctx.lineTo(7, -2);
        ctx.lineTo(13, 5);
        ctx.lineTo(8, 13);
        ctx.lineTo(-12, 13);
        ctx.lineTo(-10, 6);
        ctx.lineTo(-2, 3);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#748982";
        ctx.fillRect(-1, -10, 7, 8);
        ctx.fillRect(-9, 8, 18, 3);
        ctx.fillStyle = "#f8ffff";
        ctx.fillRect(0, -12, 7, 3);
        ctx.strokeStyle = "#273232";
        drawBadLine(-7, 4, 7, -8, "#273232", 2);
        ctx.restore();
      }

      drawSlot(x, y);
      drawSlot(x + slot + gap, y);
      drawWingBuff(x, y);
      drawBootBuff(x + slot + gap, y);
      ctx.restore();
    }

    function roundedPanelPath(x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h - r);
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
    }

    function drawPixelTomb(centerX, topY, scale = 1) {
      ctx.save();
      ctx.translate(centerX, topY);
      ctx.scale(scale, scale);
      const stoneX = -24;

      ctx.fillStyle = "rgba(0, 0, 0, 0.28)";
      ctx.fillRect(stoneX - 8, 76, 64, 7);
      ctx.fillStyle = "#aab4bd";
      ctx.fillRect(stoneX - 7, 70, 62, 11);
      ctx.fillStyle = "#d4d8da";
      ctx.fillRect(stoneX - 3, 66, 54, 8);
      ctx.strokeStyle = "#6a7078";
      ctx.lineWidth = 2;
      ctx.strokeRect(stoneX - 7, 70, 62, 11);

      const bodyGrad = ctx.createLinearGradient(stoneX, 0, stoneX + 48, 70);
      bodyGrad.addColorStop(0, "#d3d7d8");
      bodyGrad.addColorStop(0.48, "#aeb5bb");
      bodyGrad.addColorStop(1, "#7f888f");
      ctx.fillStyle = bodyGrad;
      ctx.beginPath();
      ctx.moveTo(stoneX + 10, 68);
      ctx.lineTo(stoneX + 10, 20);
      ctx.quadraticCurveTo(stoneX + 10, 5, stoneX + 24, 4);
      ctx.quadraticCurveTo(stoneX + 38, 5, stoneX + 38, 20);
      ctx.lineTo(stoneX + 38, 68);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "#565d65";
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.42)";
      ctx.fillRect(stoneX + 15, 16, 5, 48);
      ctx.fillStyle = "rgba(70, 75, 82, 0.58)";
      ctx.fillRect(stoneX + 34, 21, 3, 43);
      ctx.fillStyle = "#5f4934";
      ctx.font = "bold 9px serif";
      ctx.textAlign = "center";
      ctx.fillText("R", stoneX + 25, 28);
      ctx.fillText("I", stoneX + 25, 40);
      ctx.fillText("P", stoneX + 25, 52);
      ctx.fillStyle = "#7a5a3d";
      ctx.fillRect(stoneX + 20, 58, 9, 2);
      ctx.fillRect(stoneX + 18, 62, 13, 2);
      ctx.restore();
    }

    function drawGameOverScene(cameraY) {
      if (!gameOver) return;

      const screenX = gameOverSpot.x;
      const groundY = gameOverSpot.y - cameraY;
      const fallProgress = Math.min(1, gameOverFrame / 38);
      const stoneY = -90 + (groundY - 82 + 90) * (1 - Math.pow(1 - fallProgress, 3));
      const ghostY = groundY - 74 + Math.sin(frame * 0.12) * 8;

      ctx.save();
      ctx.fillStyle = "rgba(0, 0, 0, 0.24)";
      ctx.fillRect(0, 0, canvas.width, canvas.height - classicHudHeight);

      ctx.fillStyle = "rgba(255,255,255,0.82)";
      ctx.beginPath();
      ctx.ellipse(screenX + 34, ghostY, 19, 25, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.82)";
      ctx.beginPath();
      ctx.moveTo(screenX + 16, ghostY + 14);
      ctx.quadraticCurveTo(screenX + 24, ghostY + 31, screenX + 34, ghostY + 18);
      ctx.quadraticCurveTo(screenX + 44, ghostY + 31, screenX + 52, ghostY + 14);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#2a3442";
      ctx.fillRect(screenX + 27, ghostY - 4, 5, 6);
      ctx.fillRect(screenX + 39, ghostY - 4, 5, 6);

      const stoneTop = Math.round(stoneY);
      drawPixelTomb(screenX, stoneTop, 1);

      const dialogW = 384;
      const dialogH = 154;
      const dialogX = Math.round(canvas.width / 2 - dialogW / 2);
      const dialogY = Math.round((canvas.height - classicHudHeight) / 2 - dialogH / 2);
      const buttonW = 74;
      const buttonH = 30;
      const buttonX = dialogX + dialogW - buttonW - 16;
      const buttonY = dialogY + dialogH - buttonH - 11;
      gameOverButtonRect = { x: buttonX, y: buttonY, w: buttonW, h: buttonH };

      ctx.shadowColor = "rgba(0, 0, 0, 0.42)";
      ctx.shadowBlur = 12;
      ctx.shadowOffsetY = 4;
      const bluePanel = ctx.createLinearGradient(dialogX, dialogY, dialogX, dialogY + dialogH);
      bluePanel.addColorStop(0, "#36aee4");
      bluePanel.addColorStop(0.18, "#168ecf");
      bluePanel.addColorStop(0.58, "#0c81c6");
      bluePanel.addColorStop(1, "#0878bd");
      roundedPanelPath(dialogX, dialogY, dialogW, dialogH, 12);
      ctx.fillStyle = bluePanel;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.shadowOffsetY = 0;
      ctx.strokeStyle = "#176b9e";
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.strokeStyle = "rgba(215, 246, 255, 0.82)";
      ctx.lineWidth = 2;
      roundedPanelPath(dialogX + 4, dialogY + 4, dialogW - 8, dialogH - 8, 9);
      ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,0.12)";
      roundedPanelPath(dialogX + 8, dialogY + 7, dialogW - 16, 30, 8);
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.62)";
      ctx.beginPath();
      ctx.ellipse(dialogX + 34, dialogY + 12, 22, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      drawPixelTomb(dialogX + 52, dialogY + 48, 0.72);

      ctx.fillStyle = "#f4fbff";
      ctx.shadowColor = "rgba(0, 69, 120, 0.65)";
      ctx.shadowBlur = 2;
      ctx.font = "bold 16px Arial";
      ctx.fillText("확인을 누르시면 부활하게 됩니다.", dialogX + 105, dialogY + 40);
      ctx.font = "bold 13px Arial";
      const reviveLine1 = "마지막 세이브 지점에서";
      const reviveLine2 = "다시 도전합니다.";
      ctx.fillText(reviveLine1, dialogX + 105, dialogY + 82);
      ctx.fillText(reviveLine2, dialogX + 105, dialogY + 103);
      ctx.shadowBlur = 0;

      const buttonGrad = ctx.createLinearGradient(buttonX, buttonY, buttonX, buttonY + buttonH);
      buttonGrad.addColorStop(0, "#dfff4c");
      buttonGrad.addColorStop(0.45, "#aaf02c");
      buttonGrad.addColorStop(1, "#61b80d");
      roundedPanelPath(buttonX, buttonY, buttonW, buttonH, 7);
      ctx.fillStyle = buttonGrad;
      ctx.fill();
      ctx.strokeStyle = "#348300";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.82)";
      ctx.lineWidth = 1;
      roundedPanelPath(buttonX + 3, buttonY + 3, buttonW - 6, buttonH - 6, 5);
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 17px Arial";
      ctx.textAlign = "center";
      ctx.fillText("확인", buttonX + buttonW / 2, buttonY + 21);
      ctx.textAlign = "left";
      ctx.restore();
    }

    function drawMapleWindow(x, y, w, h, title) {
      ctx.save();
      ctx.fillStyle = "rgba(0, 0, 0, 0.42)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const panel = ctx.createLinearGradient(x, y, x, y + h);
      panel.addColorStop(0, "#6b4a19");
      panel.addColorStop(0.22, "#3d280d");
      panel.addColorStop(1, "#1c1207");
      ctx.fillStyle = panel;
      ctx.fillRect(x, y, w, h);

      ctx.strokeStyle = "#f6d877";
      ctx.lineWidth = 3;
      ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);
      ctx.strokeStyle = "#241404";
      ctx.lineWidth = 4;
      ctx.strokeRect(x + 8, y + 8, w - 16, h - 16);

      ctx.fillStyle = "rgba(16, 10, 4, 0.74)";
      ctx.fillRect(x + 16, y + 44, w - 32, h - 104);
      ctx.strokeStyle = "rgba(255, 226, 128, 0.3)";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 16, y + 44, w - 32, h - 104);

      ctx.fillStyle = "#fff2a8";
      ctx.font = "bold 23px Arial";
      ctx.textAlign = "center";
      ctx.fillText(title, x + w / 2, y + 31);
      ctx.textAlign = "left";
      ctx.restore();
    }

    function drawResultButton(x, y, w, h, label) {
      resultButtonRect = { x, y, w, h };
      const button = ctx.createLinearGradient(x, y, x, y + h);
      button.addColorStop(0, "#f8df82");
      button.addColorStop(0.48, "#c4862a");
      button.addColorStop(1, "#7a4817");
      ctx.fillStyle = button;
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "#fff5b8";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
      ctx.strokeStyle = "#3b2108";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 4, y + 4, w - 8, h - 8);
      ctx.fillStyle = "#211207";
      ctx.font = "bold 18px Arial";
      ctx.textAlign = "center";
      ctx.fillText(label, x + w / 2, y + 27);
      ctx.textAlign = "left";
    }

    function drawStageResultWindow() {
      const result = stageResults[currentStage] || {
        deaths: player.deaths,
        elapsedMs: stageFinishElapsedMs ?? 0,
      };
      const nextLabel = currentStage === visibleStageCount - 1 && hiddenUnlocked ? "히든" : "다음";
      const x = 262;
      const y = 142;
      const w = 436;
      const h = 258;
      drawMapleWindow(x, y, w, h, "STAGE CLEAR");

      ctx.fillStyle = "#f9edb2";
      ctx.font = "bold 17px Arial";
      ctx.fillText(`${currentStage + 1}단계 결과`, x + 44, y + 82);

      ctx.fillStyle = "#fff8cc";
      ctx.font = "bold 22px Arial";
      ctx.fillText("죽은 횟수", x + 82, y + 138);
      ctx.fillText(`${result.deaths}회`, x + 276, y + 138);
      ctx.fillText("소요시간", x + 82, y + 184);
      ctx.fillText(formatElapsedMs(result.elapsedMs), x + 276, y + 184);

      if (nextLabel === "히든") {
        ctx.fillStyle = "#ffdcff";
        ctx.font = "bold 14px Arial";
        ctx.fillText("3분 이내 클리어! 히든 스테이지가 열렸다.", x + 58, y + 196);
      }

      drawResultButton(x + 146, y + 210, 144, 42, nextLabel);
    }

    function drawFinalResultWindow() {
      const x = 214;
      const y = 58;
      const w = 532;
      const h = 462;
      drawMapleWindow(x, y, w, h, "FINAL RESULT");

      ctx.fillStyle = "#f9edb2";
      ctx.font = "bold 15px Arial";
      ctx.fillText("스테이지", x + 54, y + 78);
      ctx.fillText("죽음", x + 258, y + 78);
      ctx.fillText("소요시간", x + 352, y + 78);

      const resultCount = stageResults[hiddenStageIndex] ? stages.length : visibleStageCount;
      for (let i = 0; i < resultCount; i++) {
        const rowY = y + 116 + i * 38;
        const result = stageResults[i];
        ctx.fillStyle = i % 2 === 0 ? "rgba(255, 238, 160, 0.08)" : "rgba(255, 238, 160, 0.16)";
        ctx.fillRect(x + 38, rowY - 25, w - 76, 34);
        ctx.fillStyle = "#fff8cc";
        ctx.font = "bold 16px Arial";
        ctx.fillText(`${i + 1}단계`, x + 58, rowY);
        ctx.fillText(result ? `${result.deaths}회` : "--", x + 258, rowY);
        ctx.fillText(result ? formatElapsedMs(result.elapsedMs) : "--", x + 352, rowY);
      }

      const visibleResults = stageResults.slice(0, resultCount);
      const totalDeaths = visibleResults.reduce((sum, result) => sum + (result ? result.deaths : 0), 0);
      const totalTime = visibleResults.reduce((sum, result) => sum + (result ? result.elapsedMs : 0), 0);
      ctx.fillStyle = "#fff2a8";
      ctx.font = "bold 18px Arial";
      ctx.fillText(`총 죽음 ${totalDeaths}회`, x + 92, y + 374);
      ctx.fillText(`총 시간 ${formatElapsedMs(totalTime)}`, x + 286, y + 374);

      drawResultButton(x + 194, y + 396, 144, 42, "retry");
    }

    function render() {
      const playHeight = canvas.height - classicHudHeight;
      const targetCameraY = Math.max(0, Math.min(world.height - playHeight, player.y - playHeight * 0.65));
      cameraY += (targetCameraY - cameraY) * 0.12;
      drawBackground(cameraY);

      for (let i = 0; i < platforms.length; i++) drawPlatform(platforms[i], cameraY, i);
      for (const rope of ropes) drawRope(rope, cameraY);
      for (const spike of spikes) drawSpike(spike, cameraY);
      for (let i = 0; i < checkpoints.length; i++) drawCheckpoint(checkpoints[i], cameraY, i);
      for (const h of hazards) drawHazard(h, cameraY);
      drawGoal(cameraY);
      drawStartNpc(cameraY);
      if (!gameOver) drawPlayer(cameraY);
      drawMiniMap(cameraY);
      drawDummyBuffs();
      drawGameOverScene(cameraY);
      drawMapleTimePanel();
      drawClassicMapleHud();

      if (player.won) {
        const hiddenReady = currentStage === visibleStageCount - 1 && hiddenUnlocked && !stageResults[hiddenStageIndex];
        if (currentStage === hiddenStageIndex || (currentStage === visibleStageCount - 1 && !hiddenReady)) {
          drawFinalResultWindow();
        } else {
          drawStageResultWindow();
        }
      }
    }

    function loop() {
      update();
      render();
      requestAnimationFrame(loop);
    }

    function advanceResultWindow() {
      if (!player.won || !resultButtonRect) return false;

      const hiddenReady = currentStage === visibleStageCount - 1 && hiddenUnlocked && !stageResults[hiddenStageIndex];
      if (hiddenReady) {
        loadStage(hiddenStageIndex, true);
      } else if (currentStage === hiddenStageIndex || currentStage === visibleStageCount - 1) {
        stageResults = Array(stages.length).fill(null);
        hiddenUnlocked = false;
        loadStage(0);
        statusText.textContent = "처음부터 다시 도전";
      } else {
        loadStage(currentStage + 1);
      }
      return true;
    }

    window.addEventListener("keydown", (event) => {
      const key = normalizeKey(event);
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Enter", "a", "d", "w", "s", "Shift"].includes(key)) {
        event.preventDefault();
      }
      if (player.won && (key === " " || key === "Enter")) {
        advanceResultWindow();
        return;
      }
      if (key.toLowerCase() === "h") {
        hiddenUnlocked = true;
        loadStage(hiddenStageIndex, true);
        statusText.textContent = "테스트키: 히든 스테이지 진입";
        return;
      }
      keys.add(key);
    });

    window.addEventListener("keyup", (event) => keys.delete(normalizeKey(event)));
    window.addEventListener("blur", () => keys.clear());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) keys.clear();
    });

    canvas.addEventListener("click", (event) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const x = (event.clientX - rect.left) * scaleX;
      const y = (event.clientY - rect.top) * scaleY;

      if (gameOver && gameOverButtonRect) {
        const gameOverHit =
          x >= gameOverButtonRect.x &&
          x <= gameOverButtonRect.x + gameOverButtonRect.w &&
          y >= gameOverButtonRect.y &&
          y <= gameOverButtonRect.y + gameOverButtonRect.h;
        if (gameOverHit) confirmGameOver();
        return;
      }

      if (!player.won || !resultButtonRect) return;

      const hit =
        x >= resultButtonRect.x &&
        x <= resultButtonRect.x + resultButtonRect.w &&
        y >= resultButtonRect.y &&
        y <= resultButtonRect.y + resultButtonRect.h;

      if (!hit) return;

      advanceResultWindow();
    });

    restartButton.addEventListener("click", () => {
      loadStage(currentStage);
      statusText.textContent = `${stage.name} 다시 시작`;
    });

    prevStageButton.addEventListener("click", () => loadVisibleStage(currentStage - 1));
    nextStageButton.addEventListener("click", () => loadVisibleStage(currentStage + 1));

    loadStage(0);
    loop();
    </script>
"""

components.html(
    game_html.replace("__BACKGROUND_DATA_URL__", background_data_url).replace(
        "__CHARACTER_DATA_URL__",
        character_data_url,
    ).replace(
        "__PORTAL_DATA_URL__",
        portal_data_url,
    ).replace(
        "__STAR_DATA_URL__",
        star_data_url,
    ).replace(
        "__NPC_DATA_URL__",
        npc_data_url,
    ).replace(
        "__ELLINIA_EMBLEM_DATA_URL__",
        ellinia_emblem_data_url,
    ).replace(
        "__ELIXIR_DATA_URL__",
        elixir_data_url,
    ),
    height=720,
    scrolling=False,
)
