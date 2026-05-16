# MTG Proxy Card Sheet Generator

Automated tool for creating printable 3×3 proxy card sheets from individual card images using Photoshop CC 2015. Replaces the legacy AutoIt mouse-automation workflow (`TempFiles/AutoFill_MTG_PS_Sheet_v4.au3`) with proper Photoshop scripting via COM automation and ExtendScript.

## Overview

This tool takes a folder of MTG card images and produces letter-size (8.5" × 11") PNG sheets, each containing up to 9 cards in a 3×3 grid at 300 DPI — ready for printing. A PowerShell script orchestrates the process: it scans for images, groups them into batches of 9, and invokes a Photoshop ExtendScript via COM to create each sheet.

## Prerequisites

- **Windows** OS
- **Adobe Photoshop CC 2015** (must be installed and COM-registered; the script connects via `Photoshop.Application`)
- **PowerShell 5.1+** (included with Windows 10+)

## Usage

```powershell
# Basic — output goes to InputDirectory\Sheets\
.\New-MTGProxySheets.ps1 -InputDirectory "C:\Cards\MyDeck"

# Custom output directory
.\New-MTGProxySheets.ps1 -InputDirectory "C:\Cards\MyDeck" -OutputDirectory "D:\Print\Sheets"
```

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `-InputDirectory` | String | Yes | — | Path to the folder containing card images |
| `-OutputDirectory` | String | No | `<InputDirectory>\Sheets` | Path where output sheet PNGs are saved |

### Supported Image Formats

- `.png`
- `.jpg` / `.jpeg`

Images are sorted alphabetically by filename and placed left-to-right, top-to-bottom on each sheet.

## Output

- Sheet files are named `Sheet_001.png`, `Sheet_002.png`, etc.
- Each sheet is 2550 × 3300 pixels (8.5" × 11" at 300 DPI)
- Cards are sized to 770 × 1070 pixels each
- The last sheet may contain fewer than 9 cards (remaining positions are white)
- Number of sheets = ⌈total_images / 9⌉

## Grid Layout

Cards are placed in a 3×3 grid at the following center coordinates (in pixels):

```
┌──────────────────────────────────────────────┐
│  (432, 565)    (1288, 565)    (2125, 565)    │  Row 1
│                                              │
│  (432, 1655)   (1288, 1655)   (2125, 1655)   │  Row 2
│                                              │
│  (432, 2747)   (1288, 2747)   (2125, 2747)   │  Row 3
└──────────────────────────────────────────────┘
         Col 1         Col 2         Col 3
```

| Position | Grid Slot | Center X | Center Y |
|----------|-----------|----------|----------|
| 1 | Top-Left | 432 | 565 |
| 2 | Top-Center | 1288 | 565 |
| 3 | Top-Right | 2125 | 565 |
| 4 | Mid-Left | 432 | 1655 |
| 5 | Mid-Center | 1288 | 1655 |
| 6 | Mid-Right | 2125 | 1655 |
| 7 | Bot-Left | 432 | 2747 |
| 8 | Bot-Center | 1288 | 2747 |
| 9 | Bot-Right | 2125 | 2747 |

## Troubleshooting

### Photoshop not found (COM error)

```
Photoshop CC 2015 is not installed or not responding
```

- Ensure Photoshop CC 2015 is installed and has been opened at least once (to register COM)
- Try opening Photoshop manually, then re-run the script
- If you have a different Photoshop version, the COM ProgID may differ

### No images found in directory

```
No image files found in '...' Supported formats: *.png, *.jpg, *.jpeg
```

- Verify the `-InputDirectory` path is correct and contains `.png`, `.jpg`, or `.jpeg` files
- Other formats (`.bmp`, `.tiff`, `.webp`) are not supported

### Permission errors on output directory

- Ensure you have write access to the output directory
- If the directory doesn't exist, the script will create it — but needs write permission on the parent folder

### Sheet appears blank or cards mispositioned

- Verify card images are standard RGB format (CMYK images may not place correctly)
- Check that Photoshop's ruler units are set to pixels (the script sets this automatically, but Extensions can override)
- If a card image is missing, the position is left white and a warning is logged

## Testing

### Manual End-to-End Test Procedure

1. **Create a test folder** with N card images (e.g., 14 images):
   ```
   C:\test\cards\
   ├── card_01.png
   ├── card_02.png
   ├── ...
   └── card_14.jpg
   ```

2. **Run the script**:
   ```powershell
   .\New-MTGProxySheets.ps1 -InputDirectory "C:\test\cards" -OutputDirectory "C:\test\output"
   ```

3. **Verify output count**: Expected sheets = ⌈N / 9⌉
   - 14 images → 2 sheets (`Sheet_001.png` with 9 cards, `Sheet_002.png` with 5 cards)
   - 9 images → 1 sheet
   - 1 image → 1 sheet (single card, rest white)

4. **Visual inspection**: Open each output PNG and verify:
   - Cards appear at the correct grid positions (left-to-right, top-to-bottom)
   - Cards are properly sized (770 × 1070 px)
   - Partial sheets have white space in empty positions
   - No cropping, stretching, or overlap

5. **Error case tests**:
   - Run with a non-existent directory → should show "InputDirectory does not exist" error
   - Run with an empty directory → should show "No image files found" error

## Legacy Reference

This tool replaces the AutoIt v3 script at `TempFiles/AutoFill_MTG_PS_Sheet_v4.au3`, which used mouse automation to manually position cards in Photoshop. The new approach uses COM automation and ExtendScript for reliable, repeatable sheet generation without screen coordinates or mouse movement.
