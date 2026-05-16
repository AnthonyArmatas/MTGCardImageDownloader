Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$scriptDir = $PSScriptRoot

# --- Form ---
$form = New-Object System.Windows.Forms.Form
$form.Text = "MTG Proxy Card Sheet Generator"
$form.Size = New-Object System.Drawing.Size(560, 480)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

# --- Source Directory ---
$lblSource = New-Object System.Windows.Forms.Label
$lblSource.Text = "Source (card images):"
$lblSource.Location = New-Object System.Drawing.Point(15, 15)
$lblSource.AutoSize = $true
$form.Controls.Add($lblSource)

$txtSource = New-Object System.Windows.Forms.TextBox
$txtSource.Location = New-Object System.Drawing.Point(15, 35)
$txtSource.Size = New-Object System.Drawing.Size(420, 23)
$txtSource.ReadOnly = $true
$txtSource.BackColor = [System.Drawing.SystemColors]::Window
$form.Controls.Add($txtSource)

$btnSource = New-Object System.Windows.Forms.Button
$btnSource.Text = "Browse..."
$btnSource.Location = New-Object System.Drawing.Point(445, 34)
$btnSource.Size = New-Object System.Drawing.Size(85, 25)
$form.Controls.Add($btnSource)

# --- Output Directory ---
$lblOutput = New-Object System.Windows.Forms.Label
$lblOutput.Text = "Output (sheet PNGs):"
$lblOutput.Location = New-Object System.Drawing.Point(15, 68)
$lblOutput.AutoSize = $true
$form.Controls.Add($lblOutput)

$txtOutput = New-Object System.Windows.Forms.TextBox
$txtOutput.Location = New-Object System.Drawing.Point(15, 88)
$txtOutput.Size = New-Object System.Drawing.Size(420, 23)
$txtOutput.ReadOnly = $true
$txtOutput.BackColor = [System.Drawing.SystemColors]::Window
$form.Controls.Add($txtOutput)

$btnOutput = New-Object System.Windows.Forms.Button
$btnOutput.Text = "Browse..."
$btnOutput.Location = New-Object System.Drawing.Point(445, 87)
$btnOutput.Size = New-Object System.Drawing.Size(85, 25)
$form.Controls.Add($btnOutput)

# --- Generate Button ---
$btnGenerate = New-Object System.Windows.Forms.Button
$btnGenerate.Text = "Generate Sheets"
$btnGenerate.Location = New-Object System.Drawing.Point(15, 125)
$btnGenerate.Size = New-Object System.Drawing.Size(160, 35)
$btnGenerate.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnGenerate.Enabled = $false
$form.Controls.Add($btnGenerate)

# --- Open Output Button ---
$btnOpenOutput = New-Object System.Windows.Forms.Button
$btnOpenOutput.Text = "Open Output Folder"
$btnOpenOutput.Location = New-Object System.Drawing.Point(185, 125)
$btnOpenOutput.Size = New-Object System.Drawing.Size(160, 35)
$btnOpenOutput.Enabled = $false
$form.Controls.Add($btnOpenOutput)

# --- Status Log ---
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = "Status:"
$lblStatus.Location = New-Object System.Drawing.Point(15, 172)
$lblStatus.AutoSize = $true
$form.Controls.Add($lblStatus)

$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Location = New-Object System.Drawing.Point(15, 192)
$txtLog.Size = New-Object System.Drawing.Size(515, 130)
$txtLog.Multiline = $true
$txtLog.ScrollBars = "Vertical"
$txtLog.ReadOnly = $true
$txtLog.BackColor = [System.Drawing.Color]::White
$txtLog.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($txtLog)

# --- Help Text ---
$helpText = @"
What is this?
This tool creates printable 3x3 proxy card sheets from individual MTG card
images. It uses Adobe Photoshop CC 2015 to arrange up to 9 cards per
letter-size (8.5" x 11") sheet at 300 DPI, ready for printing.

How to use:
1. Click 'Browse' next to Source to pick your folder of card images (.png/.jpg)
2. Optionally pick an Output folder (defaults to Source\Sheets)
3. Click 'Generate Sheets' - Photoshop will open and create the sheets
4. Click 'Open Output Folder' to see your finished sheets

PowerShell alternative:
  .\New-MTGProxySheets.ps1 -InputDirectory "C:\Cards" -OutputDirectory "D:\Out"
"@

$txtHelp = New-Object System.Windows.Forms.TextBox
$txtHelp.Location = New-Object System.Drawing.Point(15, 332)
$txtHelp.Size = New-Object System.Drawing.Size(515, 100)
$txtHelp.Multiline = $true
$txtHelp.ScrollBars = "Vertical"
$txtHelp.ReadOnly = $true
$txtHelp.BackColor = [System.Drawing.Color]::FromArgb(245, 245, 245)
$txtHelp.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$txtHelp.Text = $helpText
$form.Controls.Add($txtHelp)

# --- Helper: update Generate button state ---
function Update-GenerateButton {
    $btnGenerate.Enabled = ($txtSource.Text -ne "")
}

# --- Helper: append to log ---
function Write-Log {
    param([string]$Message)
    $txtLog.AppendText("$Message`r`n")
    $txtLog.SelectionStart = $txtLog.Text.Length
    $txtLog.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

# --- Source Browse ---
$btnSource.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select the folder containing card images"
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -eq "OK") {
        $txtSource.Text = $dialog.SelectedPath
        if ($txtOutput.Text -eq "") {
            $txtOutput.Text = Join-Path $dialog.SelectedPath "Sheets"
        }
        Update-GenerateButton
    }
})

# --- Output Browse ---
$btnOutput.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select the output folder for sheet PNGs"
    $dialog.ShowNewFolderButton = $true
    if ($dialog.ShowDialog() -eq "OK") {
        $txtOutput.Text = $dialog.SelectedPath
    }
})

# --- Open Output Folder ---
$btnOpenOutput.Add_Click({
    if ($txtOutput.Text -ne "" -and (Test-Path $txtOutput.Text)) {
        Start-Process explorer.exe -ArgumentList $txtOutput.Text
    }
})

# --- Generate ---
$btnGenerate.Add_Click({
    $txtLog.Clear()
    $btnGenerate.Enabled = $false
    $btnOpenOutput.Enabled = $false
    $form.Cursor = [System.Windows.Forms.Cursors]::WaitCursor

    try {
        $inputDir = $txtSource.Text
        $outputDir = $txtOutput.Text

        if (-not (Test-Path $inputDir -PathType Container)) {
            Write-Log "ERROR: Source directory does not exist."
            return
        }

        # Scan for images
        $extensions = @('*.png', '*.jpg', '*.jpeg')
        $images = @()
        foreach ($ext in $extensions) {
            $images += Get-ChildItem -Path $inputDir -Filter $ext -File
        }
        $images = $images | Sort-Object -Property Name
        $totalCards = $images.Count

        if ($totalCards -eq 0) {
            Write-Log "ERROR: No image files found (.png, .jpg, .jpeg)."
            return
        }

        Write-Log "Found $totalCards card image(s)."

        # Create output directory
        if (-not (Test-Path $outputDir)) {
            New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
        }
        $outputDir = (Resolve-Path $outputDir).Path
        $txtOutput.Text = $outputDir

        $cardsPerSheet = 9
        $totalSheets = [Math]::Ceiling($totalCards / $cardsPerSheet)
        Write-Log "Creating $totalSheets sheet(s)..."

        # Read JSX
        $jsxPath = Join-Path $scriptDir 'CreateSheet.jsx'
        if (-not (Test-Path $jsxPath)) {
            Write-Log "ERROR: CreateSheet.jsx not found in $scriptDir"
            return
        }
        $jsxContent = Get-Content -Path $jsxPath -Raw

        # Connect to Photoshop
        Write-Log "Connecting to Photoshop..."
        $ps = $null
        try {
            $ps = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Photoshop.Application")
            Write-Log "Attached to running Photoshop."
        } catch {
            try {
                $ps = New-Object -ComObject Photoshop.Application
                Write-Log "Launched Photoshop."
            } catch {
                Write-Log "ERROR: Cannot connect to Photoshop. Open it first and retry."
                return
            }
        }

        $manifestPath = Join-Path $env:TEMP 'mtg_manifest.txt'
        $failedSheets = 0

        for ($i = 0; $i -lt $totalSheets; $i++) {
            $sheetNum = $i + 1
            Write-Log "Processing sheet $sheetNum of $totalSheets..."

            try {
                $startIdx = $i * $cardsPerSheet
                $endIdx = [Math]::Min($startIdx + $cardsPerSheet, $totalCards) - 1
                $batch = $images[$startIdx..$endIdx]

                $outputFileName = "Sheet_{0:D3}.png" -f $sheetNum
                $outputFilePath = Join-Path $outputDir $outputFileName

                $manifestLines = @($outputFilePath)
                foreach ($img in $batch) {
                    $manifestLines += $img.FullName
                }
                $manifestLines | Set-Content -Path $manifestPath -Encoding UTF8

                $escapedPath = $manifestPath -replace '\\', '/'
                $jsxWithManifest = "var __manifestPath = '$escapedPath';`n" + $jsxContent
                $result = $ps.DoJavascript($jsxWithManifest)

                if ($result -eq "OK") {
                    Write-Log "  Sheet $sheetNum saved: $outputFileName ($($batch.Count) cards)"
                } else {
                    Write-Log "  WARNING: Sheet $sheetNum - $result"
                    $failedSheets++
                }
            } catch {
                Write-Log "  FAILED: Sheet $sheetNum - $($_.Exception.Message)"
                $failedSheets++
            } finally {
                if (Test-Path $manifestPath) {
                    Remove-Item $manifestPath -Force -ErrorAction SilentlyContinue
                }
            }
        }

        $successSheets = $totalSheets - $failedSheets
        Write-Log ""
        Write-Log "=== Complete ==="
        Write-Log "Cards: $totalCards  |  Sheets: $successSheets of $totalSheets"
        if ($failedSheets -gt 0) {
            Write-Log "Failed: $failedSheets"
        }
        Write-Log "Output: $outputDir"

        $btnOpenOutput.Enabled = $true
    } catch {
        Write-Log "ERROR: $($_.Exception.Message)"
    } finally {
        $btnGenerate.Enabled = $true
        $form.Cursor = [System.Windows.Forms.Cursors]::Default
    }
})

[void]$form.ShowDialog()
