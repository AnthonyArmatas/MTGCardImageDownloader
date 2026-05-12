# MTG Deck Imager

A desktop application that downloads high-resolution MTG card images from [Scryfall](https://scryfall.com/) based on a pasted decklist. Built as a standalone Windows executable.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-orange)

---

## What This Is

A rewrite of the original **MTG Card Image Downloader** (Blazor Server app) as a self-contained desktop application with a modern dark-themed UI. No web server, no browser — just double-click the `.exe`.

## What Changed From The Original

### Original App (Blazor Server)
- Web-based Blazor Server app requiring `dotnet run`
- Single textarea + button on a default Blazor template
- Hard-coded download directory (`wwwroot/downloaded-pngs`)
- Only parsed one decklist format: `1 Card Name (SET) COLLECTOR`
- No progress indication
- No image previews
- Included unused boilerplate pages (Counter, Weather, Home)
- Commented-out Photoshop COM automation code

### New App (Python Desktop)
| Feature | Original | New |
|---------|----------|-----|
| **Run method** | `dotnet run` → open browser | Double-click `MTGDeckImager.exe` |
| **Directory selection** | Hard-coded path | Native folder picker dialog with path display |
| **Decklist formats** | `1 Name (SET) NUM` only | Multiple formats (see below) |
| **Progress tracking** | None | Progress bar + real-time log |
| **Image preview** | None | Thumbnail gallery of downloaded cards |
| **UI theme** | Default Blazor/Bootstrap template | Dark MTG-themed UI |
| **Scryfall lookup** | Set + collector only | Set + collector with name-search fallback |
| **Double-face cards** | Supported | Supported (unchanged) |
| **Section headers** | Not handled (would error) | Sideboard/Commander/Deck headers skipped |
| **Error handling** | Generic exception catch | Per-card error reporting in log panel |
| **Rate limiting** | None (could get throttled) | 100ms delay between API calls per Scryfall guidelines |

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

### What Was Dropped
- **Counter page** — Blazor template boilerplate, not MTG-related
- **Weather page** — Blazor template boilerplate, not MTG-related
- **Photoshop COM integration** — Was commented out and non-functional; depends on a local Photoshop install via COM interop. Could be re-added as a separate feature if needed.

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
```powershell
pip install -r requirements.txt
python build_exe.py
# Output: dist\MTGDeckImager.exe
```

## How It Works

1. **Paste a decklist** into the text area (any of the supported formats above)
2. **Pick a save folder** using the Browse button — the selected path is displayed
3. **Click "Download Cards"** — the app:
   - Parses each line to extract card name, set code, and collector number
   - Queries the Scryfall API for each card
   - Downloads the PNG image (or both faces for double-faced cards)
   - Saves files as `SET_COLLECTOR_CardName.png`
4. **Watch progress** in the progress bar and log panel
5. **Preview downloads** in the Preview tab — thumbnails appear as cards download

## Project Structure

```
MTGDeckImager/
├── mtg_deck_imager.py    # Main application (GUI + Scryfall logic)
├── build_exe.py          # PyInstaller build script
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── dist/
│   └── MTGDeckImager.exe # Standalone executable
└── build/                # PyInstaller build artifacts (generated)
```

## Technical Details

- **GUI**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — modern dark-themed Tkinter wrapper
- **API**: [Scryfall REST API](https://scryfall.com/docs/api) — free MTG card database
- **Image handling**: Pillow for thumbnail generation
- **Packaging**: PyInstaller `--onefile --windowed` for a single `.exe` with no console
- **Threading**: Downloads run in a background thread to keep the UI responsive
- **Rate limiting**: 100ms between Scryfall requests per their [good citizenship guidelines](https://scryfall.com/docs/api)
