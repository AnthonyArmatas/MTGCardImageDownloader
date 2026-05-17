# MTG Deck Imager

A desktop application that downloads high-resolution MTG card images from [Scryfall](https://scryfall.com/) based on a pasted decklist. Built as a standalone Windows executable.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-orange)

---

## What This Is

A rewrite of the original **MTG Card Image Downloader** (Blazor Server app) as a self-contained desktop application with a modern dark-themed UI. No web server, no browser — just double-click the `.exe`.

## Features

### ⬇ Download Cards
Paste a decklist, pick a folder, download high-res PNGs from Scryfall.
- Multiple decklist formats (see below)
- Handles single-face and double-face cards
- Progress bar, real-time log, and thumbnail previews
- 100ms rate limiting per Scryfall guidelines

### 📄 Proxy Sheets
Generate printable 3×3 card sheets (8.5"×11" at 300 DPI) from a folder of card images.
- **Photoshop (COM)** engine — uses ExtendScript via `CreateSheet.jsx` (requires Adobe Photoshop)
- **Built-in (Pillow)** engine — pure Python, no Photoshop needed, identical output
- Auto-falls back to Pillow if Photoshop fails
- Output: `Sheet_001.png`, `Sheet_002.png`, etc.

### 🎨 Art Swap
Replace card art with custom images using frame templates.
- **Single Frame mode** — one frame template + many art images → many proxies
- **Paired mode** — N frames + N art images → matched by alphabetical sort order
- Cover-fit scaling (no stretch/squash) — preserves aspect ratio automatically
- Works with any image size or resolution

**How to create a frame template:** Open a card in Photoshop, erase the center art area so it's transparent, save as PNG. The tool detects the transparent region and fills it with your art.

## What Changed From The Original

### Original App (Blazor Server)
- Web-based Blazor Server app requiring `dotnet run`
- Single textarea + button on a default Blazor template
- Hard-coded download directory (`wwwroot/downloaded-pngs`)
- Only parsed one decklist format: `1 Card Name (SET) COLLECTOR`
- No progress indication, no image previews
- Commented-out Photoshop COM automation code (non-functional)

### New App (Python Desktop)
| Feature | Original | New |
|---------|----------|-----|
| **Run method** | `dotnet run` → open browser | Double-click `MTGDeckImager.exe` |
| **Directory selection** | Hard-coded path | Native folder picker dialog with path display |
| **Decklist formats** | `1 Name (SET) NUM` only | Multiple formats (see below) |
| **Progress tracking** | None | Progress bar + real-time log |
| **Image preview** | None | Thumbnail gallery of downloaded cards |
| **UI theme** | Default Blazor/Bootstrap template | Dark MTG-themed UI with tabs |
| **Proxy sheets** | None | 3×3 grid sheets via Photoshop COM or Pillow |
| **Art swap** | None | Frame template + custom art compositing |
| **Error handling** | Generic exception catch | Per-card error reporting in log panel |
| **Rate limiting** | None (could get throttled) | 100ms delay between API calls |

### Supported Decklist Formats
```
1 Asceticism (PLST) SOM-110       # Set + collector number
1 Asceticism (SOM) 110            # Set + collector number
4 Lightning Bolt (M11)            # Set code, name search
4 Lightning Bolt                  # Name search (any printing)
1x Lightning Bolt                 # "1x" quantity prefix
Sideboard                         # Section headers (skipped)
// comment                        # Comments (skipped)
```

## How To Run

### Option A: Run the .exe directly
```
dist\MTGDeckImager.exe
```
Double-click it. No Python installation required.

### Option B: Run from source
```powershell
pip install -r requirements.txt
python mtg_deck_imager.py
```

### Option C: Rebuild the .exe

Double-click `build.cmd`, or from a terminal:
```powershell
.\build.cmd
```

This installs dependencies and rebuilds `dist\MTGDeckImager.exe`. Requires Python 3.10+ on PATH.

You can also build manually:
```powershell
pip install -r requirements.txt
python build_exe.py
```

## Project Structure

```
MTGDeckImager/
├── mtg_deck_imager.py    # Main application (GUI + all features)
├── CreateSheet.jsx       # Photoshop ExtendScript for proxy sheet generation
├── build_exe.py          # PyInstaller build script (Python)
├── build.cmd             # One-click build (installs deps + builds exe)
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── dist/
│   └── MTGDeckImager.exe # Standalone executable
└── build/                # PyInstaller build artifacts (generated)
```

## Technical Details

- **GUI**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — modern dark-themed Tkinter wrapper
- **API**: [Scryfall REST API](https://scryfall.com/docs/api) — free MTG card database
- **Image handling**: Pillow for thumbnails, proxy sheets, and art swap compositing
- **Photoshop integration**: COM automation via pywin32 + ExtendScript (`CreateSheet.jsx`)
- **Packaging**: PyInstaller `--onefile --windowed` for a single `.exe` with no console window
- **Threading**: All heavy operations run in background threads to keep the UI responsive
- **Rate limiting**: 100ms between Scryfall requests per their [good citizenship guidelines](https://scryfall.com/docs/api)
