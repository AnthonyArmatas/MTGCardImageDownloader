// =============================================================================
// CreateSheet.jsx — Photoshop ExtendScript for MTG Proxy Card Sheet Generation
// =============================================================================
// Called by New-MTGProxySheets.ps1 via COM DoJavascript.
// Reads a manifest file path from arguments[0].
// Manifest format: line 1 = output PNG path, lines 2+ = card image paths.
// Creates a 3x3 grid sheet at 2550x3300 px / 300 DPI.
// =============================================================================

// --- Configuration -----------------------------------------------------------
var CANVAS_WIDTH   = 2550;   // 8.5" at 300 DPI
var CANVAS_HEIGHT  = 3300;   // 11" at 300 DPI
var RESOLUTION     = 300;    // DPI
var CARD_WIDTH     = 770;    // pixels
var CARD_HEIGHT    = 1070;   // pixels

// Grid position centers (column, row) — left-to-right, top-to-bottom
var COL_CENTERS = [432, 1288, 2125];  // 3 columns
var ROW_CENTERS = [565, 1655, 2747];  // 3 rows

// Pre-computed grid positions array: index 0 = top-left, index 8 = bottom-right
var GRID_POSITIONS = [];
for (var r = 0; r < ROW_CENTERS.length; r++) {
    for (var c = 0; c < COL_CENTERS.length; c++) {
        GRID_POSITIONS.push({ x: COL_CENTERS[c], y: ROW_CENTERS[r] });
    }
}

// --- Main Logic --------------------------------------------------------------

// Ensure pixel units
app.preferences.rulerUnits = Units.PIXELS;

try {
    // Read manifest path — injected as __manifestPath by PowerShell,
    // or fall back to arguments[0] if run standalone.
    var manifestPath = (typeof __manifestPath !== 'undefined') ? __manifestPath : arguments[0];
    var manifestFile = new File(manifestPath);

    if (!manifestFile.exists) {
        throw new Error("Manifest file not found: " + manifestPath);
    }

    // Read manifest lines
    manifestFile.open("r");
    var manifestContent = manifestFile.read();
    manifestFile.close();

    var lines = manifestContent.split(/[\r\n]+/);
    // Remove empty lines
    var cleanLines = [];
    for (var i = 0; i < lines.length; i++) {
        var trimmed = lines[i].replace(/^\s+|\s+$/g, "");
        if (trimmed.length > 0) {
            cleanLines.push(trimmed);
        }
    }

    if (cleanLines.length < 2) {
        throw new Error("Manifest must have at least 2 lines (output path + 1 image)");
    }

    var outputPath = cleanLines[0];
    var imagePaths = cleanLines.slice(1);

    // Create new document
    var doc = app.documents.add(
        CANVAS_WIDTH,
        CANVAS_HEIGHT,
        RESOLUTION,
        "ProxySheet",
        NewDocumentMode.RGB,
        DocumentFill.WHITE
    );

    // Place each card image
    for (var idx = 0; idx < imagePaths.length && idx < 9; idx++) {
        var imgFile = new File(imagePaths[idx]);
        if (!imgFile.exists) {
            $.writeln("WARNING: Image not found, skipping position " + (idx + 1) + ": " + imagePaths[idx]);
            continue;
        }

        // Open the card image as a separate document
        var cardDoc = app.open(imgFile);

        // Flatten in case it has layers, then select all and copy
        cardDoc.flatten();
        cardDoc.selection.selectAll();
        cardDoc.selection.copy();
        cardDoc.close(SaveOptions.DONOTSAVECHANGES);

        // Switch back to our sheet document and paste
        app.activeDocument = doc;
        doc.paste();

        // The pasted layer is now the active layer
        var layer = doc.activeLayer;

        // Get current bounds: [left, top, right, bottom]
        var bounds = layer.bounds;
        var curWidth = bounds[2].as("px") - bounds[0].as("px");
        var curHeight = bounds[3].as("px") - bounds[1].as("px");

        // Calculate scale percentages to reach target card size
        var scaleX = (CARD_WIDTH / curWidth) * 100;
        var scaleY = (CARD_HEIGHT / curHeight) * 100;
        layer.resize(scaleX, scaleY, AnchorPosition.MIDDLECENTER);

        // Get updated bounds after resize
        bounds = layer.bounds;
        var curCenterX = (bounds[0].as("px") + bounds[2].as("px")) / 2;
        var curCenterY = (bounds[1].as("px") + bounds[3].as("px")) / 2;

        // Calculate translation delta to target grid position
        var targetX = GRID_POSITIONS[idx].x;
        var targetY = GRID_POSITIONS[idx].y;
        var deltaX = targetX - curCenterX;
        var deltaY = targetY - curCenterY;

        layer.translate(new UnitValue(deltaX, "px"), new UnitValue(deltaY, "px"));
    }

    // Flatten all layers
    doc.flatten();

    // Save as PNG
    var pngOpts = new PNGSaveOptions();
    pngOpts.compression = 6;
    pngOpts.interlaced = false;
    var outFile = new File(outputPath);
    doc.saveAs(outFile, pngOpts, true, Extension.LOWERCASE);

    // Close without saving PSD
    doc.close(SaveOptions.DONOTSAVECHANGES);

    "OK";
} catch (e) {
    $.writeln("ERROR: " + e.message);
    "ERROR: " + e.message;
}
