<#
.SYNOPSIS
    Creates printable proxy card sheets from a directory of MTG card images.

.DESCRIPTION
    Scans a directory for card images, groups them into batches of 9,
    and uses Photoshop CC 2015 via COM automation to create 3x3 grid
    sheets at 300 DPI on letter-size (8.5" x 11") pages.

.PARAMETER InputDirectory
    Path to the folder containing card images (*.png, *.jpg, *.jpeg).

.PARAMETER OutputDirectory
    Path to the folder where sheet PNGs will be saved.
    Defaults to a 'Sheets' subfolder inside InputDirectory.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputDirectory,

    [Parameter(Mandatory = $false)]
    [string]$OutputDirectory
)

#region Configuration
$Config = @{
    CanvasWidth      = 2550          # 8.5" at 300 DPI
    CanvasHeight     = 3300          # 11" at 300 DPI
    Resolution       = 300           # DPI
    CardWidth        = 770           # pixels
    CardHeight       = 1070          # pixels
    ColumnCenters    = @(432, 1288, 2125)  # 3 columns
    RowCenters       = @(565, 1655, 2747)  # 3 rows
    CardsPerSheet    = 9             # 3x3 grid
    SupportedExtensions = @('*.png', '*.jpg', '*.jpeg')
}
#endregion Configuration

$ErrorActionPreference = 'Stop'

# Validate InputDirectory exists
if (-not (Test-Path $InputDirectory -PathType Container)) {
    throw "InputDirectory does not exist: '$InputDirectory'"
}

# Default OutputDirectory to InputDirectory\Sheets
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $InputDirectory 'Sheets'
}

# Resolve to absolute paths
$InputDirectory = (Resolve-Path $InputDirectory).Path
$jsxPath = Join-Path $PSScriptRoot 'CreateSheet.jsx'

# Create output directory if it doesn't exist
if (-not (Test-Path $OutputDirectory)) {
    New-Item -Path $OutputDirectory -ItemType Directory -Force | Out-Null
}
$OutputDirectory = (Resolve-Path $OutputDirectory).Path

# Scan for image files
$images = @()
foreach ($ext in $Config.SupportedExtensions) {
    $images += Get-ChildItem -Path $InputDirectory -Filter $ext -File
}

# Sort alphabetically by filename
$images = $images | Sort-Object -Property Name

$totalCards = $images.Count
Write-Host "Found $totalCards card image(s) in '$InputDirectory'"

if ($totalCards -eq 0) {
    throw "No image files found in '$InputDirectory'. Supported formats: $($Config.SupportedExtensions -join ', ')"
}

# Calculate batch count
$totalSheets = [Math]::Ceiling($totalCards / $Config.CardsPerSheet)
Write-Host "Will create $totalSheets sheet(s) in '$OutputDirectory'"

# Read JSX content
$jsxContent = Get-Content -Path $jsxPath -Raw

# Connect to Photoshop via COM
# Prefer attaching to a running instance first (avoids elevation/UAC mismatch).
# If Photoshop is not running, fall back to creating a new instance.
$ps = $null
try {
    $ps = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Photoshop.Application")
    Write-Host "Attached to running Photoshop instance."
} catch {
    Write-Verbose "No running Photoshop instance found, launching new one..."
    try {
        $ps = New-Object -ComObject Photoshop.Application
        Write-Host "Launched new Photoshop instance."
    } catch {
        throw ("Failed to connect to Photoshop. " +
               "If running PowerShell as Administrator, try running it without elevation instead. " +
               "Alternatively, open Photoshop first and re-run the script. " +
               "COM error: $($_.Exception.Message)")
    }
}

$manifestPath = Join-Path $env:TEMP 'mtg_manifest.txt'
$failedSheets = 0

# Process batches
for ($batchIndex = 0; $batchIndex -lt $totalSheets; $batchIndex++) {
    $sheetNumber = $batchIndex + 1
    Write-Host "Processing sheet $sheetNumber of $totalSheets..."

    try {
        # Slice the images for this batch
        $startIdx = $batchIndex * $Config.CardsPerSheet
        $endIdx = [Math]::Min($startIdx + $Config.CardsPerSheet, $totalCards) - 1
        $batchImages = $images[$startIdx..$endIdx]

        # Build output filename: Sheet_001.png, Sheet_002.png, etc.
        $outputFileName = "Sheet_{0:D3}.png" -f $sheetNumber
        $outputFilePath = Join-Path $OutputDirectory $outputFileName

        # Write manifest file
        $manifestLines = @($outputFilePath)
        foreach ($img in $batchImages) {
            $manifestLines += $img.FullName
        }
        $manifestLines | Set-Content -Path $manifestPath -Encoding UTF8

        # Invoke Photoshop via COM DoJavascript
        # Embed the manifest path as a JS variable — DoJavascript argument passing
        # is unreliable across PS CC versions, so we inject it into the script text.
        $escapedPath = $manifestPath -replace '\\', '/'
        $jsxWithManifest = "var __manifestPath = '$escapedPath';`n" + $jsxContent
        $result = $ps.DoJavascript($jsxWithManifest)

        if ($result -eq "OK") {
            Write-Host "  Sheet $sheetNumber saved: $outputFileName ($($batchImages.Count) cards)"
        } else {
            Write-Warning "  Sheet $sheetNumber may have issues. Photoshop returned: $result"
            $failedSheets++
        }
    } catch {
        Write-Warning "  Sheet $sheetNumber FAILED: $($_.Exception.Message)"
        $failedSheets++
    } finally {
        # Clean up temp manifest after each batch
        if (Test-Path $manifestPath) {
            Remove-Item $manifestPath -Force -ErrorAction SilentlyContinue
        }
    }
}

# Summary
$successSheets = $totalSheets - $failedSheets
Write-Host ""
Write-Host "=== Complete ==="
Write-Host "Cards processed: $totalCards"
Write-Host "Sheets created:  $successSheets of $totalSheets"
if ($failedSheets -gt 0) {
    Write-Host "Sheets failed:   $failedSheets"
}
Write-Host "Output directory: $OutputDirectory"