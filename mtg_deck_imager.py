"""
MTG Deck Imager — Scryfall card image downloader with a modern GUI.

Paste a decklist, pick a folder, and download high-res PNGs from Scryfall.
Supports single-face and double-face cards, multiple decklist formats,
image previews, and progress tracking.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import requests
import threading
import re
import os
import io
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
        self.geometry("1100x780")
        self.minsize(900, 650)
        self.configure(fg_color=BG_DARK)

        # State
        self.download_dir: str | None = None
        self.is_downloading = False
        self.thumbnail_refs: list = []  # prevent GC of PhotoImage refs

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
            banner, text="Download card art from Scryfall",
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

        # ── Directory picker ──────────────────────────────────────────────
        dir_frame = ctk.CTkFrame(left, fg_color="transparent")
        dir_frame.pack(fill="x", padx=16, pady=(16, 8))

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
            left, text="Decklist",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_LIGHT,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.decklist_box = ctk.CTkTextbox(
            left, height=220, fg_color="#0f1626",
            text_color=TEXT_LIGHT,
            font=ctk.CTkFont(family="Consolas", size=13),
            corner_radius=8,
            border_width=1, border_color="#2a3a5a",
        )
        self.decklist_box.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.decklist_box.insert(
            "1.0",
            "# Paste your decklist here\n"
            "# Supported formats:\n"
            "#   4 Lightning Bolt\n"
            "#   1 Asceticism (SOM) 110\n"
            "#   2x Counterspell (MH2)\n"
        )

        # ── Controls row ──────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(left, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 12))

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
            left, fg_color="#0f1626", progress_color=ACCENT,
            height=6, corner_radius=3,
        )
        self.progress.pack(fill="x", padx=16, pady=(0, 4))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            left, text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#667788",
        )
        self.status_label.pack(anchor="w", padx=16, pady=(0, 12))

    def _build_right_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ── Tab view: Log / Preview ───────────────────────────────────────
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

        # Preview tab
        preview_tab = self.tabview.add("Preview")
        self.preview_scroll = ctk.CTkScrollableFrame(
            preview_tab, fg_color="#0f1626", corner_radius=8,
        )
        self.preview_scroll.pack(fill="both", expand=True)

    # ── Actions ───────────────────────────────────────────────────────────

    def _pick_directory(self):
        folder = filedialog.askdirectory(title="Select download folder")
        if folder:
            self.download_dir = folder
            # Show abbreviated path if long
            display = folder
            if len(display) > 55:
                display = "…" + display[-52:]
            self.dir_label.configure(text=display, text_color=SUCCESS_GREEN)

    def _clear_all(self):
        self.decklist_box.delete("1.0", "end")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress.set(0)
        self.status_label.configure(text="Ready", text_color="#667788")
        # Clear preview thumbnails
        for widget in self.preview_scroll.winfo_children():
            widget.destroy()
        self.thumbnail_refs.clear()

    def _log(self, msg: str, color: str = TEXT_LIGHT):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str, color: str = "#667788"):
        self.status_label.configure(text=text, text_color=color)

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
                        # Add thumbnail preview
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

        # Summary
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
        """Add a card thumbnail to the preview panel."""
        try:
            img = Image.open(path)
            # Scale to ~140px wide for thumbnail
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
            pass  # thumbnail is a nice-to-have, don't crash


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MTGDeckImager()
    app.mainloop()
