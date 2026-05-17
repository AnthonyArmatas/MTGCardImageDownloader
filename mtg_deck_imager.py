"""
MTG Deck Imager — Scryfall card image downloader with a modern GUI.

Paste a decklist, pick a folder, and download high-res PNGs from Scryfall.
Supports single-face and double-face cards, multiple decklist formats,
image previews, progress tracking, and proxy sheet generation.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import requests
import threading
import re
import os
import sys
import io
import math
import time
from pathlib import Path


# ── Scryfall API helpers ──────────────────────────────────────────────────────

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/named"
SCRYFALL_SET = "https://api.scryfall.com/cards/{set_code}/{collector_num}"
HEADERS = {"User-Agent": "MTGDeckImager/2.0", "Accept": "application/json"}

# Scryfall asks for 50-100ms between requests
RATE_LIMIT_SECONDS = 0.1


def parse_decklist(text: str) -> list[dict]:
    """
    Parse a decklist into structured entries.

    Supported formats:
      1 Asceticism (PLST) SOM-110        → set + collector
      1 Asceticism (SOM) 110             → set + collector
      4 Lightning Bolt (M11)             → set, search by name
      4 Lightning Bolt                   → search by name (any printing)
      1x Lightning Bolt                  → '1x' quantity prefix
      Sideboard / Commander / etc.       → section headers (skipped)
    """
    entries = []
    lines = text.strip().splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Skip section headers like "Sideboard", "Commander", "Deck", "Companion"
        if re.match(r'^(Sideboard|Commander|Deck|Companion|Maybeboard)\s*$', line, re.IGNORECASE):
            continue
        # Skip comment lines
        if line.startswith("//") or line.startswith("#"):
            continue

        # Try: QTY [x] NAME (SET) COLLECTOR
        m = re.match(
            r'^(\d+)\s*x?\s+(.+?)\s+\((\w+)\)\s+(\S+)\s*$', line
        )
        if m:
            entries.append({
                "qty": int(m.group(1)),
                "name": m.group(2).strip(),
                "set": m.group(3).upper(),
                "collector": m.group(4),
            })
            continue

        # Try: QTY [x] NAME (SET)
        m = re.match(r'^(\d+)\s*x?\s+(.+?)\s+\((\w+)\)\s*$', line)
        if m:
            entries.append({
                "qty": int(m.group(1)),
                "name": m.group(2).strip(),
                "set": m.group(3).upper(),
                "collector": None,
            })
            continue

        # Try: QTY [x] NAME
        m = re.match(r'^(\d+)\s*x?\s+(.+?)\s*$', line)
        if m:
            entries.append({
                "qty": int(m.group(1)),
                "name": m.group(2).strip(),
                "set": None,
                "collector": None,
            })
            continue

        # Bare card name (no quantity)
        if line and not line[0].isdigit():
            entries.append({
                "qty": 1,
                "name": line,
                "set": None,
                "collector": None,
            })

    return entries


def fetch_card_json(session: requests.Session, entry: dict) -> dict | None:
    """Fetch card JSON from Scryfall for one entry."""
    if entry["set"] and entry["collector"]:
        url = SCRYFALL_SET.format(
            set_code=entry["set"].lower(),
            collector_num=entry["collector"],
        )
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()

    # Fallback: search by exact name (optionally scoped to set)
    params = {"exact": entry["name"]}
    if entry["set"]:
        params["set"] = entry["set"].lower()
    resp = session.get(SCRYFALL_SEARCH, params=params, headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        return resp.json()

    return None


def extract_image_urls(card_json: dict) -> list[tuple[str, str]]:
    """
    Return list of (filename_label, png_url) for a card.
    Handles single-face and multi-face cards.
    """
    results = []
    name = card_json.get("name", "unknown")
    set_code = card_json.get("set", "xxx").upper()
    collector = card_json.get("collector_number", "0")

    if "image_uris" in card_json:
        png = card_json["image_uris"].get("png")
        if png:
            safe = re.sub(r'\W+', '_', name)
            results.append((f"{set_code}_{collector}_{safe}.png", png))
    elif "card_faces" in card_json:
        for face in card_json["card_faces"]:
            face_name = face.get("name", "face")
            imgs = face.get("image_uris", {})
            png = imgs.get("png")
            if png:
                safe = re.sub(r'\W+', '_', face_name)
                results.append((f"{set_code}_{collector}_{safe}.png", png))

    return results


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    """Download a single image file. Returns True on success."""
    resp = session.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 200:
        dest.write_bytes(resp.content)
        return True
    return False


# ── Proxy Sheet Generation ────────────────────────────────────────────────────

# Sheet layout constants — identical to the original MTGProxySheets
SHEET_WIDTH = 2550       # 8.5" at 300 DPI
SHEET_HEIGHT = 3300      # 11" at 300 DPI
SHEET_DPI = 300
CARD_WIDTH = 770         # pixels
CARD_HEIGHT = 1070       # pixels
COL_CENTERS = [432, 1288, 2125]
ROW_CENTERS = [565, 1655, 2747]
CARDS_PER_SHEET = 9

# Pre-compute grid positions (top-left corner for each slot)
GRID_POSITIONS = []
for _r in ROW_CENTERS:
    for _c in COL_CENTERS:
        GRID_POSITIONS.append((_c - CARD_WIDTH // 2, _r - CARD_HEIGHT // 2))

SUPPORTED_IMG_EXTS = {".png", ".jpg", ".jpeg"}


def get_card_images(folder: Path) -> list[Path]:
    """Get sorted list of card image files from a folder."""
    images = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMG_EXTS
    ]
    images.sort(key=lambda p: p.name.lower())
    return images


def generate_sheet_pillow(
    image_paths: list[Path],
    output_path: Path,
    on_log=None,
) -> bool:
    """
    Generate a single 3x3 proxy sheet using Pillow (no Photoshop needed).
    Returns True on success.
    """
    try:
        sheet = Image.new("RGB", (SHEET_WIDTH, SHEET_HEIGHT), "white")

        for idx, img_path in enumerate(image_paths[:CARDS_PER_SHEET]):
            card = Image.open(img_path)
            card = card.resize((CARD_WIDTH, CARD_HEIGHT), Image.LANCZOS)
            x, y = GRID_POSITIONS[idx]
            sheet.paste(card, (x, y))
            card.close()

        sheet.save(str(output_path), "PNG", dpi=(SHEET_DPI, SHEET_DPI))
        sheet.close()
        return True
    except Exception as exc:
        if on_log:
            on_log(f"❌ Pillow error: {exc}")
        return False


def generate_sheets_pillow(
    source_dir: Path,
    output_dir: Path,
    on_log=None,
    on_progress=None,
) -> tuple[int, int]:
    """
    Generate all proxy sheets from a folder of card images using Pillow.
    Returns (success_count, fail_count).
    """
    images = get_card_images(source_dir)
    if not images:
        if on_log:
            on_log("❌ No image files found (.png, .jpg, .jpeg)")
        return 0, 0

    output_dir.mkdir(parents=True, exist_ok=True)
    total_sheets = math.ceil(len(images) / CARDS_PER_SHEET)

    if on_log:
        on_log(f"📋 Found {len(images)} card image(s)")
        on_log(f"📄 Creating {total_sheets} sheet(s)…")

    success = 0
    fail = 0

    for i in range(total_sheets):
        batch = images[i * CARDS_PER_SHEET : (i + 1) * CARDS_PER_SHEET]
        filename = f"Sheet_{i + 1:03d}.png"
        out_path = output_dir / filename

        if on_log:
            on_log(f"  Processing sheet {i + 1}/{total_sheets}…")

        ok = generate_sheet_pillow(batch, out_path, on_log)
        if ok:
            success += 1
            if on_log:
                on_log(f"  ✅ {filename} ({len(batch)} cards)")
        else:
            fail += 1

        if on_progress:
            on_progress((i + 1) / total_sheets)

    return success, fail


def check_photoshop_available() -> bool:
    """Check if Photoshop COM automation is available."""
    try:
        import win32com.client
        return True
    except ImportError:
        return False


def get_jsx_path() -> Path:
    """Get path to CreateSheet.jsx, handling both source and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return Path(sys._MEIPASS) / "CreateSheet.jsx"
    else:
        return Path(__file__).parent / "CreateSheet.jsx"


def generate_sheets_photoshop(
    source_dir: Path,
    output_dir: Path,
    on_log=None,
    on_progress=None,
) -> tuple[int, int]:
    """
    Generate all proxy sheets using Photoshop COM + ExtendScript.
    Returns (success_count, fail_count).
    """
    import win32com.client
    import tempfile

    images = get_card_images(source_dir)
    if not images:
        if on_log:
            on_log("❌ No image files found (.png, .jpg, .jpeg)")
        return 0, 0

    output_dir.mkdir(parents=True, exist_ok=True)
    total_sheets = math.ceil(len(images) / CARDS_PER_SHEET)

    if on_log:
        on_log(f"📋 Found {len(images)} card image(s)")
        on_log(f"📄 Creating {total_sheets} sheet(s) via Photoshop…")

    # Read JSX content
    jsx_path = get_jsx_path()
    if not jsx_path.exists():
        if on_log:
            on_log(f"❌ CreateSheet.jsx not found at {jsx_path}")
        return 0, total_sheets

    jsx_content = jsx_path.read_text(encoding="utf-8")

    # Connect to Photoshop
    ps = None
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            ps = win32com.client.GetActiveObject("Photoshop.Application")
            if on_log:
                on_log("🔗 Attached to running Photoshop instance")
        except Exception:
            ps = win32com.client.Dispatch("Photoshop.Application")
            if on_log:
                on_log("🚀 Launched Photoshop")
    except Exception as exc:
        if on_log:
            on_log(f"❌ Cannot connect to Photoshop: {exc}")
            on_log("💡 Try opening Photoshop manually first, or use Built-in mode")
        return 0, total_sheets

    success = 0
    fail = 0

    for i in range(total_sheets):
        batch = images[i * CARDS_PER_SHEET : (i + 1) * CARDS_PER_SHEET]
        filename = f"Sheet_{i + 1:03d}.png"
        out_path = output_dir / filename

        if on_log:
            on_log(f"  Processing sheet {i + 1}/{total_sheets}…")

        try:
            # Write manifest file (same format as original)
            manifest_path = Path(tempfile.gettempdir()) / "mtg_manifest.txt"
            manifest_lines = [str(out_path)] + [str(p) for p in batch]
            manifest_path.write_text("\n".join(manifest_lines), encoding="utf-8")

            # Write the complete JSX to a temp file and run via DoJavascriptFile.
            # DoJavascript with large inline strings fails through Python COM dispatch.
            escaped = str(manifest_path).replace("\\", "/")
            jsx_with_manifest = f"var __manifestPath = '{escaped}';\n" + jsx_content
            jsx_tmp = Path(tempfile.gettempdir()) / "mtg_sheet_run.jsx"
            jsx_tmp.write_text(jsx_with_manifest, encoding="utf-8")

            result = ps.DoJavascriptFile(str(jsx_tmp))

            if result == "OK":
                success += 1
                if on_log:
                    on_log(f"  ✅ {filename} ({len(batch)} cards)")
            else:
                fail += 1
                if on_log:
                    on_log(f"  ⚠️ {filename}: {result}")

            # Clean up temp files
            if manifest_path.exists():
                manifest_path.unlink()
            if jsx_tmp.exists():
                jsx_tmp.unlink()

        except Exception as exc:
            fail += 1
            if on_log:
                on_log(f"  ❌ {filename}: {exc}")

        if on_progress:
            on_progress((i + 1) / total_sheets)

    return success, fail


# ── Art Swap (Proxy Art Replacement) ──────────────────────────────────────────

def find_art_box(frame_img: Image.Image) -> tuple[int, int, int, int] | None:
    """
    Detect the art box in a frame template by finding the bounding box of
    the transparent (alpha=0) region. Returns (left, top, right, bottom)
    or None if no transparent region found.
    """
    if frame_img.mode != "RGBA":
        return None

    alpha = frame_img.split()[3]  # alpha channel
    # Invert: we want the bounding box of the transparent region
    # getbbox() finds non-zero pixels, so invert alpha first
    from PIL import ImageOps
    inverted = ImageOps.invert(alpha)
    bbox = inverted.getbbox()
    return bbox


def cover_fit(art: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """
    Scale art to cover the box while preserving aspect ratio (cover-fit).
    The art is scaled so the *smaller* dimension fills the box, then
    center-cropped to exact box size. No stretching or squashing.
    """
    art_w, art_h = art.size
    scale = max(box_w / art_w, box_h / art_h)
    new_w = round(art_w * scale)
    new_h = round(art_h * scale)
    art_scaled = art.resize((new_w, new_h), Image.LANCZOS)

    # Center crop to exact box size
    left = (new_w - box_w) // 2
    top = (new_h - box_h) // 2
    return art_scaled.crop((left, top, left + box_w, top + box_h))


def swap_art_single(
    frame_path: Path,
    art_path: Path,
    output_path: Path,
    on_log=None,
) -> bool:
    """
    Composite one card: art underneath, frame template on top.
    The frame template must be a PNG with a transparent hole where the art goes.
    Returns True on success.
    """
    try:
        frame = Image.open(frame_path).convert("RGBA")
        art = Image.open(art_path).convert("RGBA")

        art_box = find_art_box(frame)
        if art_box is None:
            if on_log:
                on_log(f"⚠️  No transparent region in {frame_path.name} — skipping")
            return False

        left, top, right, bottom = art_box
        box_w = right - left
        box_h = bottom - top

        # Cover-fit the art to the box
        art_fitted = cover_fit(art, box_w, box_h)

        # Composite: start with white background at frame size
        result = Image.new("RGBA", frame.size, (255, 255, 255, 255))
        # Paste fitted art into the art box position
        result.paste(art_fitted, (left, top))
        # Paste frame on top (with alpha)
        result = Image.alpha_composite(result, frame)

        # Save as RGB PNG (no alpha in final output)
        result.convert("RGB").save(str(output_path), "PNG")

        frame.close()
        art.close()
        return True
    except Exception as exc:
        if on_log:
            on_log(f"❌ Art swap error ({art_path.name}): {exc}")
        return False


def swap_art_batch(
    frame_path: Path,
    art_dir: Path,
    output_dir: Path,
    on_log=None,
    on_progress=None,
) -> tuple[int, int]:
    """
    Batch art swap: one frame template + folder of art images → folder of proxies.
    Each art image gets composited with the same frame.
    Returns (success_count, fail_count).
    """
    art_images = [
        f for f in art_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMG_EXTS
    ]
    art_images.sort(key=lambda p: p.name.lower())

    if not art_images:
        if on_log:
            on_log("❌ No art images found (.png, .jpg, .jpeg)")
        return 0, 0

    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(art_images)

    if on_log:
        on_log(f"📋 Found {total} art image(s)")
        on_log(f"🖼️  Frame: {frame_path.name}")
        on_log(f"📁 Output: {output_dir}")

    success = 0
    fail = 0

    for idx, art_path in enumerate(art_images):
        out_name = f"proxy_{art_path.stem}.png"
        out_path = output_dir / out_name

        ok = swap_art_single(frame_path, art_path, out_path, on_log)
        if ok:
            success += 1
            if on_log:
                on_log(f"  ✅ {out_name}")
        else:
            fail += 1

        if on_progress:
            on_progress((idx + 1) / total)

    return success, fail


def swap_art_paired(
    frames_dir: Path,
    art_dir: Path,
    output_dir: Path,
    on_log=None,
    on_progress=None,
) -> tuple[int, int]:
    """
    Paired art swap: match frame templates to art images by sorted order.
    Frame 1 + Art 1 → Proxy 1, Frame 2 + Art 2 → Proxy 2, etc.
    Returns (success_count, fail_count).
    """
    frames = [
        f for f in frames_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMG_EXTS
    ]
    frames.sort(key=lambda p: p.name.lower())

    arts = [
        f for f in art_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMG_EXTS
    ]
    arts.sort(key=lambda p: p.name.lower())

    if not frames:
        if on_log:
            on_log("❌ No frame templates found")
        return 0, 0
    if not arts:
        if on_log:
            on_log("❌ No art images found")
        return 0, 0

    output_dir.mkdir(parents=True, exist_ok=True)
    pairs = list(zip(frames, arts))
    total = len(pairs)

    if on_log:
        on_log(f"📋 Pairing {len(frames)} frame(s) with {len(arts)} art image(s)")
        on_log(f"   → {total} pair(s) to process")
        if len(frames) != len(arts):
            on_log(f"   ⚠️  Counts differ — extra files will be skipped")

    success = 0
    fail = 0

    for idx, (frame_path, art_path) in enumerate(pairs):
        out_name = f"proxy_{art_path.stem}.png"
        out_path = output_dir / out_name

        ok = swap_art_single(frame_path, art_path, out_path, on_log)
        if ok:
            success += 1
            if on_log:
                on_log(f"  ✅ {out_name} ({frame_path.name} + {art_path.name})")
        else:
            fail += 1

        if on_progress:
            on_progress((idx + 1) / total)

    return success, fail


# ── GUI Application ───────────────────────────────────────────────────────────

# Theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colors for the MTG-themed look
BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
ACCENT = "#e94560"
ACCENT_HOVER = "#c73e54"
TEXT_LIGHT = "#eaeaea"
SUCCESS_GREEN = "#00d474"
WARN_AMBER = "#ffa726"
ERROR_RED = "#ef5350"


class MTGDeckImager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MTG Deck Imager")
        self.geometry("1100x820")
        self.minsize(900, 700)
        self.configure(fg_color=BG_DARK)

        # State
        self.download_dir: str | None = None
        self.sheets_source_dir: str | None = None
        self.sheets_output_dir: str | None = None
        self.swap_frame_path: str | None = None
        self.swap_frames_dir: str | None = None
        self.swap_art_dir: str | None = None
        self.swap_output_dir: str | None = None
        self.is_downloading = False
        self.is_generating_sheets = False
        self.is_swapping_art = False
        self.thumbnail_refs: list = []  # prevent GC of PhotoImage refs
        self.sheet_thumb_refs: list = []
        self.swap_thumb_refs: list = []
        self.ps_available = check_photoshop_available()

        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top banner
        banner = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=56)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        ctk.CTkLabel(
            banner, text="⚔  MTG Deck Imager",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left", padx=20)
        ctk.CTkLabel(
            banner, text="Download  ·  Proxy Sheets  ·  Art Swap",
            font=ctk.CTkFont(size=13),
            text_color="#8899aa",
        ).pack(side="left", padx=8)

        # Main content — two-column layout
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(12, 16))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    def _build_left_panel(self, parent):
        left = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # Left-side tabview: Download | Sheets
        self.left_tabs = ctk.CTkTabview(
            left, fg_color=BG_CARD, segmented_button_fg_color="#0f1626",
            segmented_button_selected_color=ACCENT,
            segmented_button_unselected_color="#1e2d4a",
            corner_radius=8,
        )
        self.left_tabs.pack(fill="both", expand=True, padx=8, pady=8)

        dl_tab = self.left_tabs.add("⬇ Download")
        sheets_tab = self.left_tabs.add("📄 Proxy Sheets")
        swap_tab = self.left_tabs.add("🎨 Art Swap")

        self._build_download_tab(dl_tab)
        self._build_sheets_tab(sheets_tab)
        self._build_swap_tab(swap_tab)

    def _build_download_tab(self, tab):
        # ── Directory picker ──────────────────────────────────────────────
        dir_frame = ctk.CTkFrame(tab, fg_color="transparent")
        dir_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            dir_frame, text="Save Location",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        dir_row = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_row.pack(fill="x", pady=(4, 0))

        self.dir_label = ctk.CTkLabel(
            dir_row,
            text="No folder selected",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.dir_label.pack(side="left", fill="x", expand=True)

        self.browse_btn = ctk.CTkButton(
            dir_row, text="Browse…", width=100,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._pick_directory,
        )
        self.browse_btn.pack(side="right")

        # ── Decklist input ────────────────────────────────────────────────
        ctk.CTkLabel(
            tab, text="Decklist",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w", padx=8, pady=(8, 4))

        self.decklist_box = ctk.CTkTextbox(
            tab, height=220, fg_color="#0f1626",
            text_color=TEXT_LIGHT,
            font=ctk.CTkFont(family="Consolas", size=13),
            corner_radius=8,
            border_width=1, border_color="#2a3a5a",
        )
        self.decklist_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.decklist_box.insert(
            "1.0",
            "# Paste your decklist here\n"
            "# Supported formats:\n"
            "#   4 Lightning Bolt\n"
            "#   1 Asceticism (SOM) 110\n"
            "#   2x Counterspell (MH2)\n"
        )

        # ── Controls row ──────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", padx=8, pady=(0, 8))

        self.download_btn = ctk.CTkButton(
            ctrl, text="⬇  Download Cards", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._start_download,
        )
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            ctrl, text="Clear", width=80, height=40,
            fg_color="#2a2a4a", hover_color="#3a3a5a",
            command=self._clear_all,
        )
        self.clear_btn.pack(side="right")

        # ── Progress bar ──────────────────────────────────────────────────
        self.progress = ctk.CTkProgressBar(
            tab, fg_color="#0f1626", progress_color=ACCENT,
            height=6, corner_radius=3,
        )
        self.progress.pack(fill="x", padx=8, pady=(0, 4))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            tab, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#667788",
        )
        self.status_label.pack(anchor="w", padx=8, pady=(0, 8))

    def _build_sheets_tab(self, tab):
        # ── Source directory ───────────────────────────────────────────────
        src_frame = ctk.CTkFrame(tab, fg_color="transparent")
        src_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            src_frame, text="Source (card images folder)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        src_row = ctk.CTkFrame(src_frame, fg_color="transparent")
        src_row.pack(fill="x", pady=(4, 0))

        self.sheets_src_label = ctk.CTkLabel(
            src_row,
            text="No folder selected — or use download folder →",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.sheets_src_label.pack(side="left", fill="x", expand=True)

        src_btns = ctk.CTkFrame(src_row, fg_color="transparent")
        src_btns.pack(side="right")

        ctk.CTkButton(
            src_btns, text="Use Download Dir", width=130,
            fg_color="#2a2a4a", hover_color="#3a3a5a",
            command=self._sheets_use_download_dir,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            src_btns, text="Browse…", width=80,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._sheets_pick_source,
        ).pack(side="left")

        # ── Output directory ──────────────────────────────────────────────
        out_frame = ctk.CTkFrame(tab, fg_color="transparent")
        out_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            out_frame, text="Output (sheet PNGs)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        out_row = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_row.pack(fill="x", pady=(4, 0))

        self.sheets_out_label = ctk.CTkLabel(
            out_row,
            text="Defaults to Source\\Sheets",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.sheets_out_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            out_row, text="Browse…", width=80,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._sheets_pick_output,
        ).pack(side="right")

        # ── Engine selector ───────────────────────────────────────────────
        engine_frame = ctk.CTkFrame(tab, fg_color="transparent")
        engine_frame.pack(fill="x", padx=8, pady=(12, 4))

        ctk.CTkLabel(
            engine_frame, text="Engine",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(side="left")

        engines = ["Built-in (Pillow)"]
        default_engine = "Built-in (Pillow)"
        if self.ps_available:
            engines.insert(0, "Photoshop (COM)")
            default_engine = "Photoshop (COM)"

        self.engine_var = ctk.StringVar(value=default_engine)
        self.engine_menu = ctk.CTkOptionMenu(
            engine_frame,
            variable=self.engine_var,
            values=engines,
            fg_color="#0f1626",
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            width=200,
        )
        self.engine_menu.pack(side="left", padx=(12, 0))

        if not self.ps_available:
            ctk.CTkLabel(
                engine_frame,
                text="(pywin32 not installed — Photoshop unavailable)",
                font=ctk.CTkFont(size=11),
                text_color=WARN_AMBER,
            ).pack(side="left", padx=(8, 0))

        # ── Info label ────────────────────────────────────────────────────
        info_text = (
            "Creates printable 3×3 proxy sheets (8.5\"×11\" at 300 DPI).\n"
            "Each sheet holds up to 9 cards. Images are sorted alphabetically.\n"
            "Output: Sheet_001.png, Sheet_002.png, etc."
        )
        ctk.CTkLabel(
            tab, text=info_text,
            font=ctk.CTkFont(size=11),
            text_color="#556677",
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))

        # ── Generate button ───────────────────────────────────────────────
        gen_ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        gen_ctrl.pack(fill="x", padx=8, pady=(8, 8))

        self.generate_btn = ctk.CTkButton(
            gen_ctrl, text="📄  Generate Proxy Sheets", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._start_sheet_generation,
        )
        self.generate_btn.pack(side="left", fill="x", expand=True)

        # ── Sheet progress ────────────────────────────────────────────────
        self.sheet_progress = ctk.CTkProgressBar(
            tab, fg_color="#0f1626", progress_color=SUCCESS_GREEN,
            height=6, corner_radius=3,
        )
        self.sheet_progress.pack(fill="x", padx=8, pady=(8, 4))
        self.sheet_progress.set(0)

        self.sheet_status_label = ctk.CTkLabel(
            tab, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#667788",
        )
        self.sheet_status_label.pack(anchor="w", padx=8, pady=(0, 8))

    def _build_swap_tab(self, tab):
        # ── Mode selector ─────────────────────────────────────────────────
        mode_frame = ctk.CTkFrame(tab, fg_color="transparent")
        mode_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            mode_frame, text="Mode",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(side="left")

        self.swap_mode_var = ctk.StringVar(value="Single Frame + Art Folder")
        self.swap_mode_menu = ctk.CTkOptionMenu(
            mode_frame,
            variable=self.swap_mode_var,
            values=["Single Frame + Art Folder", "Paired (Frames Folder + Art Folder)"],
            fg_color="#0f1626",
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            width=290,
            command=self._swap_mode_changed,
        )
        self.swap_mode_menu.pack(side="left", padx=(12, 0))

        # ── Frame template (single file) ──────────────────────────────────
        self.swap_frame_single = ctk.CTkFrame(tab, fg_color="transparent")
        self.swap_frame_single.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            self.swap_frame_single, text="Frame Template (PNG with transparent art hole)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        sf_row = ctk.CTkFrame(self.swap_frame_single, fg_color="transparent")
        sf_row.pack(fill="x", pady=(4, 0))

        self.swap_frame_label = ctk.CTkLabel(
            sf_row,
            text="No file selected",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.swap_frame_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            sf_row, text="Pick File…", width=90,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._swap_pick_frame_file,
        ).pack(side="right")

        # ── Frames folder (paired mode) ───────────────────────────────────
        self.swap_frames_folder = ctk.CTkFrame(tab, fg_color="transparent")
        # Hidden by default (single mode active)

        ctk.CTkLabel(
            self.swap_frames_folder, text="Frames Folder (each frame paired to art by sort order)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        ff_row = ctk.CTkFrame(self.swap_frames_folder, fg_color="transparent")
        ff_row.pack(fill="x", pady=(4, 0))

        self.swap_frames_dir_label = ctk.CTkLabel(
            ff_row,
            text="No folder selected",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.swap_frames_dir_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            ff_row, text="Browse…", width=80,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._swap_pick_frames_dir,
        ).pack(side="right")

        # ── Art folder ────────────────────────────────────────────────────
        art_frame = ctk.CTkFrame(tab, fg_color="transparent")
        art_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            art_frame, text="Art Images Folder",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        art_row = ctk.CTkFrame(art_frame, fg_color="transparent")
        art_row.pack(fill="x", pady=(4, 0))

        self.swap_art_label = ctk.CTkLabel(
            art_row,
            text="No folder selected",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.swap_art_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            art_row, text="Browse…", width=80,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._swap_pick_art_dir,
        ).pack(side="right")

        # ── Output folder ─────────────────────────────────────────────────
        out_frame = ctk.CTkFrame(tab, fg_color="transparent")
        out_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            out_frame, text="Output Folder",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w")

        out_row = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_row.pack(fill="x", pady=(4, 0))

        self.swap_out_label = ctk.CTkLabel(
            out_row,
            text="Defaults to Art Folder\\Proxies",
            font=ctk.CTkFont(size=12),
            text_color="#667788",
            anchor="w",
        )
        self.swap_out_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            out_row, text="Browse…", width=80,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._swap_pick_output_dir,
        ).pack(side="right")

        # ── Info ──────────────────────────────────────────────────────────
        info_text = (
            "How it works:\n"
            "1. Create a frame template: open a card in Photoshop, erase the\n"
            "   art area so it's transparent, save as PNG\n"
            "2. Pick your replacement art images\n"
            "3. The tool does cover-fit (no stretch) and composites automatically\n"
            "\n"
            "Single mode: 1 frame + many art images → many proxies\n"
            "Paired mode: N frames + N art images → matched by sort order"
        )
        ctk.CTkLabel(
            tab, text=info_text,
            font=ctk.CTkFont(size=11),
            text_color="#556677",
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))

        # ── Generate button ───────────────────────────────────────────────
        swap_ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        swap_ctrl.pack(fill="x", padx=8, pady=(8, 8))

        self.swap_btn = ctk.CTkButton(
            swap_ctrl, text="🎨  Swap Art", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._start_art_swap,
        )
        self.swap_btn.pack(side="left", fill="x", expand=True)

        # ── Progress ──────────────────────────────────────────────────────
        self.swap_progress = ctk.CTkProgressBar(
            tab, fg_color="#0f1626", progress_color=SUCCESS_GREEN,
            height=6, corner_radius=3,
        )
        self.swap_progress.pack(fill="x", padx=8, pady=(8, 4))
        self.swap_progress.set(0)

        self.swap_status_label = ctk.CTkLabel(
            tab, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#667788",
        )
        self.swap_status_label.pack(anchor="w", padx=8, pady=(0, 8))

    def _build_right_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ── Tab view: Log / Preview / Sheets ──────────────────────────────
        self.tabview = ctk.CTkTabview(
            right, fg_color=BG_CARD, segmented_button_fg_color="#0f1626",
            segmented_button_selected_color=ACCENT,
            segmented_button_unselected_color="#1e2d4a",
            corner_radius=8,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        # Log tab
        log_tab = self.tabview.add("Log")
        self.log_box = ctk.CTkTextbox(
            log_tab, fg_color="#0f1626", text_color=TEXT_LIGHT,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8, state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)

        # Preview tab (card thumbnails)
        preview_tab = self.tabview.add("Preview")
        self.preview_scroll = ctk.CTkScrollableFrame(
            preview_tab, fg_color="#0f1626", corner_radius=8,
        )
        self.preview_scroll.pack(fill="both", expand=True)

        # Sheets tab (generated sheet previews)
        sheets_preview_tab = self.tabview.add("Sheets")
        self.sheets_preview_scroll = ctk.CTkScrollableFrame(
            sheets_preview_tab, fg_color="#0f1626", corner_radius=8,
        )
        self.sheets_preview_scroll.pack(fill="both", expand=True)

        # Art Swap tab (proxy previews)
        swap_preview_tab = self.tabview.add("Art Swap")
        self.swap_preview_scroll = ctk.CTkScrollableFrame(
            swap_preview_tab, fg_color="#0f1626", corner_radius=8,
        )
        self.swap_preview_scroll.pack(fill="both", expand=True)

    # ── Directory Actions ─────────────────────────────────────────────────

    def _pick_directory(self):
        folder = filedialog.askdirectory(title="Select download folder")
        if folder:
            self.download_dir = folder
            display = folder
            if len(display) > 55:
                display = "…" + display[-52:]
            self.dir_label.configure(text=display, text_color=SUCCESS_GREEN)

    def _sheets_pick_source(self):
        folder = filedialog.askdirectory(title="Select card images folder")
        if folder:
            self.sheets_source_dir = folder
            display = folder
            if len(display) > 45:
                display = "…" + display[-42:]
            self.sheets_src_label.configure(text=display, text_color=SUCCESS_GREEN)
            # Auto-set output if not already set
            if not self.sheets_output_dir:
                out = str(Path(folder) / "Sheets")
                self.sheets_output_dir = out
                self.sheets_out_label.configure(text=out, text_color=TEXT_LIGHT)

    def _sheets_pick_output(self):
        folder = filedialog.askdirectory(title="Select output folder for sheets")
        if folder:
            self.sheets_output_dir = folder
            display = folder
            if len(display) > 45:
                display = "…" + display[-42:]
            self.sheets_out_label.configure(text=display, text_color=SUCCESS_GREEN)

    def _sheets_use_download_dir(self):
        if not self.download_dir:
            messagebox.showinfo(
                "No download folder",
                "Pick a download folder on the Download tab first."
            )
            return
        self.sheets_source_dir = self.download_dir
        display = self.download_dir
        if len(display) > 45:
            display = "…" + display[-42:]
        self.sheets_src_label.configure(text=display, text_color=SUCCESS_GREEN)
        # Auto-set output
        out = str(Path(self.download_dir) / "Sheets")
        self.sheets_output_dir = out
        self.sheets_out_label.configure(text=out, text_color=TEXT_LIGHT)

    # ── Clear ─────────────────────────────────────────────────────────────

    def _clear_all(self):
        self.decklist_box.delete("1.0", "end")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress.set(0)
        self.status_label.configure(text="Ready", text_color="#667788")
        for widget in self.preview_scroll.winfo_children():
            widget.destroy()
        self.thumbnail_refs.clear()

    # ── Logging ───────────────────────────────────────────────────────────

    def _log(self, msg: str, color: str = TEXT_LIGHT):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str, color: str = "#667788"):
        self.status_label.configure(text=text, text_color=color)

    # ── Download Logic ────────────────────────────────────────────────────

    def _start_download(self):
        if self.is_downloading:
            return

        text = self.decklist_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty decklist", "Paste a decklist first.")
            return
        if not self.download_dir:
            messagebox.showwarning("No folder", "Pick a save location first.")
            return

        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="Downloading…")
        self.progress.set(0)

        # Clear previous log/preview
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        for widget in self.preview_scroll.winfo_children():
            widget.destroy()
        self.thumbnail_refs.clear()

        # Switch to Log tab
        self.tabview.set("Log")

        thread = threading.Thread(
            target=self._download_worker, args=(text,), daemon=True
        )
        thread.start()

    def _download_worker(self, text: str):
        entries = parse_decklist(text)
        if not entries:
            self.after(0, lambda: self._log("❓ No cards found in decklist."))
            self.after(0, self._download_done)
            return

        total = len(entries)
        self.after(0, lambda: self._log(f"📋 Parsed {total} unique card(s)"))
        self.after(0, lambda: self._log(f"📂 Saving to: {self.download_dir}"))
        self.after(0, lambda: self._set_status(f"Downloading 0/{total}…", ACCENT))

        dest = Path(self.download_dir)
        dest.mkdir(parents=True, exist_ok=True)

        success_count = 0
        fail_count = 0
        session = requests.Session()

        for idx, entry in enumerate(entries):
            label = entry["name"]
            if entry["set"]:
                label += f" ({entry['set']})"

            self.after(0, lambda l=label: self._set_status(
                f"Downloading {l}…", ACCENT
            ))

            try:
                card = fetch_card_json(session, entry)
                if card is None:
                    self.after(0, lambda l=label: self._log(f"❌ Not found: {l}"))
                    fail_count += 1
                    time.sleep(RATE_LIMIT_SECONDS)
                    continue

                urls = extract_image_urls(card)
                if not urls:
                    self.after(0, lambda l=label: self._log(
                        f"⚠️  No PNG for: {l}"
                    ))
                    fail_count += 1
                    time.sleep(RATE_LIMIT_SECONDS)
                    continue

                for filename, png_url in urls:
                    file_path = dest / filename
                    ok = download_image(session, png_url, file_path)
                    if ok:
                        success_count += 1
                        self.after(0, lambda f=filename: self._log(f"✅ {f}"))
                        self.after(0, lambda p=file_path: self._add_thumbnail(p))
                    else:
                        fail_count += 1
                        self.after(0, lambda f=filename: self._log(
                            f"❌ Failed: {f}"
                        ))
                    time.sleep(RATE_LIMIT_SECONDS)

            except Exception as exc:
                self.after(0, lambda l=label, e=str(exc): self._log(
                    f"❌ {l}: {e}"
                ))
                fail_count += 1

            prog = (idx + 1) / total
            self.after(0, lambda p=prog: self.progress.set(p))

        summary = f"Done — {success_count} saved, {fail_count} failed"
        color = SUCCESS_GREEN if fail_count == 0 else WARN_AMBER
        self.after(0, lambda: self._log(f"\n{'─'*40}"))
        self.after(0, lambda s=summary: self._log(s))
        self.after(0, lambda s=summary, c=color: self._set_status(s, c))
        self.after(0, self._download_done)

    def _download_done(self):
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="⬇  Download Cards")
        self.progress.set(1)

    def _add_thumbnail(self, path: Path):
        try:
            img = Image.open(path)
            ratio = 140 / img.width
            thumb_size = (140, int(img.height * ratio))
            img = img.resize(thumb_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.thumbnail_refs.append(photo)

            lbl = ctk.CTkLabel(
                self.preview_scroll, image=photo, text="",
            )
            lbl.pack(side="left", padx=4, pady=4)
        except Exception:
            pass

    # ── Sheet Generation Logic ────────────────────────────────────────────

    def _start_sheet_generation(self):
        if self.is_generating_sheets:
            return

        if not self.sheets_source_dir:
            messagebox.showwarning(
                "No source folder",
                "Pick a source folder of card images first."
            )
            return

        source = Path(self.sheets_source_dir)
        if not source.is_dir():
            messagebox.showerror("Invalid folder", f"Source folder does not exist:\n{source}")
            return

        output = Path(self.sheets_output_dir) if self.sheets_output_dir else source / "Sheets"
        self.sheets_output_dir = str(output)

        engine = self.engine_var.get()

        self.is_generating_sheets = True
        self.generate_btn.configure(state="disabled", text="Generating…")
        self.sheet_progress.set(0)

        # Clear sheet previews
        for widget in self.sheets_preview_scroll.winfo_children():
            widget.destroy()
        self.sheet_thumb_refs.clear()

        # Clear and switch to log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.tabview.set("Log")

        thread = threading.Thread(
            target=self._sheet_worker,
            args=(source, output, engine),
            daemon=True,
        )
        thread.start()

    def _sheet_worker(self, source: Path, output: Path, engine: str):
        def on_log(msg):
            self.after(0, lambda m=msg: self._log(m))

        def on_progress(p):
            self.after(0, lambda v=p: self.sheet_progress.set(v))

        self.after(0, lambda: self._log(f"🔧 Engine: {engine}"))
        self.after(0, lambda: self._log(f"📂 Source: {source}"))
        self.after(0, lambda: self._log(f"📁 Output: {output}"))
        self.after(0, lambda: self.sheet_status_label.configure(
            text="Generating sheets…", text_color=ACCENT
        ))

        use_photoshop = engine.startswith("Photoshop")

        if use_photoshop:
            try:
                success, fail = generate_sheets_photoshop(
                    source, output, on_log, on_progress
                )
            except Exception as exc:
                on_log(f"❌ Photoshop failed: {exc}")
                on_log("⚠️  Falling back to Built-in (Pillow)…")
                success, fail = generate_sheets_pillow(
                    source, output, on_log, on_progress
                )
        else:
            success, fail = generate_sheets_pillow(
                source, output, on_log, on_progress
            )

        # Summary
        total = success + fail
        summary = f"Sheets: {success}/{total} created"
        color = SUCCESS_GREEN if fail == 0 else WARN_AMBER
        self.after(0, lambda: self._log(f"\n{'─'*40}"))
        self.after(0, lambda s=summary: self._log(s))
        self.after(0, lambda s=summary, c=color: self.sheet_status_label.configure(
            text=s, text_color=c
        ))

        # Add sheet preview thumbnails
        if output.is_dir():
            sheets = sorted(output.glob("Sheet_*.png"))
            for sp in sheets:
                self.after(0, lambda p=sp: self._add_sheet_thumbnail(p))

        self.after(0, self._sheet_generation_done)

    def _sheet_generation_done(self):
        self.is_generating_sheets = False
        self.generate_btn.configure(state="normal", text="📄  Generate Proxy Sheets")
        self.sheet_progress.set(1)
        # Switch right panel to Sheets tab to show previews
        self.tabview.set("Sheets")

    def _add_sheet_thumbnail(self, path: Path):
        try:
            img = Image.open(path)
            # Scale to ~280px wide for sheet preview
            ratio = 280 / img.width
            thumb_size = (280, int(img.height * ratio))
            img = img.resize(thumb_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.sheet_thumb_refs.append(photo)

            frame = ctk.CTkFrame(self.sheets_preview_scroll, fg_color="transparent")
            frame.pack(pady=6, padx=4)

            ctk.CTkLabel(
                frame, image=photo, text="",
            ).pack()

            ctk.CTkLabel(
                frame, text=path.name,
                font=ctk.CTkFont(size=11),
                text_color="#8899aa",
            ).pack()
        except Exception:
            pass


    # ── Art Swap Logic ────────────────────────────────────────────────────

    def _swap_mode_changed(self, value):
        if value.startswith("Single"):
            self.swap_frame_single.pack(fill="x", padx=8, pady=(8, 4))
            self.swap_frames_folder.pack_forget()
        else:
            self.swap_frame_single.pack_forget()
            self.swap_frames_folder.pack(fill="x", padx=8, pady=(8, 4))

    def _swap_pick_frame_file(self):
        path = filedialog.askopenfilename(
            title="Select frame template PNG",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if path:
            self.swap_frame_path = path
            name = Path(path).name
            self.swap_frame_label.configure(text=name, text_color=SUCCESS_GREEN)

    def _swap_pick_frames_dir(self):
        folder = filedialog.askdirectory(title="Select frames folder")
        if folder:
            self.swap_frames_dir = folder
            display = folder if len(folder) <= 45 else "…" + folder[-42:]
            self.swap_frames_dir_label.configure(text=display, text_color=SUCCESS_GREEN)

    def _swap_pick_art_dir(self):
        folder = filedialog.askdirectory(title="Select art images folder")
        if folder:
            self.swap_art_dir = folder
            display = folder if len(folder) <= 45 else "…" + folder[-42:]
            self.swap_art_label.configure(text=display, text_color=SUCCESS_GREEN)
            if not self.swap_output_dir:
                out = str(Path(folder) / "Proxies")
                self.swap_output_dir = out
                self.swap_out_label.configure(text=out, text_color=TEXT_LIGHT)

    def _swap_pick_output_dir(self):
        folder = filedialog.askdirectory(title="Select output folder for proxies")
        if folder:
            self.swap_output_dir = folder
            display = folder if len(folder) <= 45 else "…" + folder[-42:]
            self.swap_out_label.configure(text=display, text_color=SUCCESS_GREEN)

    def _start_art_swap(self):
        if self.is_swapping_art:
            return

        mode = self.swap_mode_var.get()
        is_single = mode.startswith("Single")

        if is_single and not self.swap_frame_path:
            messagebox.showwarning("No frame", "Pick a frame template file first.")
            return
        if not is_single and not self.swap_frames_dir:
            messagebox.showwarning("No frames folder", "Pick a frames folder first.")
            return
        if not self.swap_art_dir:
            messagebox.showwarning("No art folder", "Pick an art images folder first.")
            return

        art_dir = Path(self.swap_art_dir)
        if not art_dir.is_dir():
            messagebox.showerror("Invalid folder", f"Art folder does not exist:\n{art_dir}")
            return

        output = Path(self.swap_output_dir) if self.swap_output_dir else art_dir / "Proxies"
        self.swap_output_dir = str(output)

        self.is_swapping_art = True
        self.swap_btn.configure(state="disabled", text="Swapping…")
        self.swap_progress.set(0)

        # Clear swap previews
        for widget in self.swap_preview_scroll.winfo_children():
            widget.destroy()
        self.swap_thumb_refs.clear()

        # Clear and switch to log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.tabview.set("Log")

        if is_single:
            frame_path = Path(self.swap_frame_path)
            thread = threading.Thread(
                target=self._swap_worker_single,
                args=(frame_path, art_dir, output),
                daemon=True,
            )
        else:
            frames_dir = Path(self.swap_frames_dir)
            thread = threading.Thread(
                target=self._swap_worker_paired,
                args=(frames_dir, art_dir, output),
                daemon=True,
            )
        thread.start()

    def _swap_worker_single(self, frame_path: Path, art_dir: Path, output: Path):
        def on_log(msg):
            self.after(0, lambda m=msg: self._log(m))

        def on_progress(p):
            self.after(0, lambda v=p: self.swap_progress.set(v))

        self.after(0, lambda: self._log("🎨 Art Swap — Single Frame mode"))
        self.after(0, lambda: self.swap_status_label.configure(
            text="Swapping art…", text_color=ACCENT
        ))

        success, fail = swap_art_batch(frame_path, art_dir, output, on_log, on_progress)
        self._swap_finish(success, fail, output)

    def _swap_worker_paired(self, frames_dir: Path, art_dir: Path, output: Path):
        def on_log(msg):
            self.after(0, lambda m=msg: self._log(m))

        def on_progress(p):
            self.after(0, lambda v=p: self.swap_progress.set(v))

        self.after(0, lambda: self._log("🎨 Art Swap — Paired mode"))
        self.after(0, lambda: self.swap_status_label.configure(
            text="Swapping art…", text_color=ACCENT
        ))

        success, fail = swap_art_paired(frames_dir, art_dir, output, on_log, on_progress)
        self._swap_finish(success, fail, output)

    def _swap_finish(self, success: int, fail: int, output: Path):
        total = success + fail
        summary = f"Art Swap: {success}/{total} created"
        color = SUCCESS_GREEN if fail == 0 else WARN_AMBER
        self.after(0, lambda: self._log(f"\n{'─'*40}"))
        self.after(0, lambda s=summary: self._log(s))
        self.after(0, lambda s=summary, c=color: self.swap_status_label.configure(
            text=s, text_color=c
        ))

        # Add proxy previews
        if output.is_dir():
            proxies = sorted(output.glob("proxy_*.png"))
            for p in proxies:
                self.after(0, lambda path=p: self._add_swap_thumbnail(path))

        self.after(0, self._swap_done)

    def _swap_done(self):
        self.is_swapping_art = False
        self.swap_btn.configure(state="normal", text="🎨  Swap Art")
        self.swap_progress.set(1)
        self.tabview.set("Art Swap")

    def _add_swap_thumbnail(self, path: Path):
        try:
            img = Image.open(path)
            ratio = 160 / img.width
            thumb_size = (160, int(img.height * ratio))
            img = img.resize(thumb_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.swap_thumb_refs.append(photo)

            frame = ctk.CTkFrame(self.swap_preview_scroll, fg_color="transparent")
            frame.pack(side="left", pady=4, padx=4)

            ctk.CTkLabel(frame, image=photo, text="").pack()
            ctk.CTkLabel(
                frame, text=path.name,
                font=ctk.CTkFont(size=10),
                text_color="#8899aa",
            ).pack()
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MTGDeckImager()
    app.mainloop()
