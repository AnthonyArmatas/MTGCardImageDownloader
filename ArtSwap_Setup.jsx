// =============================================================================
// ArtSwap_Setup.jsx — Photoshop ExtendScript: Prepare a card for art replacement
// =============================================================================
//
// Usage:
//   1. Open a card image in Photoshop
//   2. Run this script (File → Scripts → Browse → ArtSwap_Setup.jsx)
//   3. When prompted, pick your replacement art file
//   4. The script will:
//      - Create a "Frame" layer from the card (with art area cut out)
//      - Place your art as a layer underneath, cover-fit scaled
//      - Leave you in Move Tool so you can drag the art into position
//   5. When you're happy with the position, run ArtSwap_Export.jsx
//
// The art box is detected by prompting you to make a rectangular selection
// around the art area BEFORE running the script, OR it uses a standard
// MTG card art box if no selection is active.
//
// Works with any card size/resolution — positions are calculated as
// percentages of the card dimensions.
// =============================================================================

#target photoshop

app.preferences.rulerUnits = Units.PIXELS;

// --- Standard art box ratios (percentage of card dimensions) -----------------
// These are approximate for a standard MTG card frame.
// Left, Top, Right, Bottom as fraction of card width/height.
// ADJUST THESE if the cutout doesn't match your cards:
var STD_ART_LEFT   = 0.084;   // ~8.4% from left edge
var STD_ART_TOP    = 0.125;   // ~12.5% from top (below title bar)
var STD_ART_RIGHT  = 0.916;   // ~91.6% from left
var STD_ART_BOTTOM = 0.538;   // ~53.8% from top (above type line)

// Extra inward padding (pixels) — increase to cut less into the frame
var PADDING = 3;

// =============================================================================

try {
    if (app.documents.length === 0) {
        alert("Open a card image first, then run this script.");
        throw "No document open";
    }

    var doc = app.activeDocument;
    var cardW = doc.width.as("px");
    var cardH = doc.height.as("px");

    // --- Determine the art box region ----------------------------------------
    var artLeft, artTop, artRight, artBottom;
    var hasSelection = false;

    try {
        // Check if user has made a selection
        var selBounds = doc.selection.bounds;
        artLeft   = selBounds[0].as("px");
        artTop    = selBounds[1].as("px");
        artRight  = selBounds[2].as("px");
        artBottom = selBounds[3].as("px");
        hasSelection = true;
    } catch (e) {
        // No selection — use standard ratios + padding
        artLeft   = Math.round(cardW * STD_ART_LEFT)  + PADDING;
        artTop    = Math.round(cardH * STD_ART_TOP)   + PADDING;
        artRight  = Math.round(cardW * STD_ART_RIGHT)  - PADDING;
        artBottom = Math.round(cardH * STD_ART_BOTTOM) - PADDING;
    }

    var artBoxW = artRight - artLeft;
    var artBoxH = artBottom - artTop;

    if (artBoxW < 10 || artBoxH < 10) {
        alert("Art box is too small. Make a rectangular selection around the art area and try again.");
        throw "Art box too small";
    }

    // --- Ask user for the replacement art file --------------------------------
    var artFile = File.openDialog("Select replacement art image", "Image Files:*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.psd", false);
    if (!artFile) {
        throw "No art file selected";
    }

    // --- Set up layers --------------------------------------------------------
    // Flatten the card to a single layer first
    doc.flatten();

    // Rename the background layer to "Frame"
    doc.activeLayer.name = "Frame";

    // Select the art box area
    var selRegion = [
        [artLeft, artTop],
        [artRight, artTop],
        [artRight, artBottom],
        [artLeft, artBottom]
    ];
    doc.selection.select(selRegion);

    // Delete the art area from the Frame layer (makes it transparent)
    // First convert background to normal layer if needed
    doc.activeLayer.isBackgroundLayer = false;
    doc.selection.clear();
    doc.selection.deselect();

    // --- Place the replacement art -------------------------------------------
    // Open the art file
    var artDoc = app.open(artFile);
    var artW = artDoc.width.as("px");
    var artH = artDoc.height.as("px");

    // Flatten and copy
    artDoc.flatten();
    artDoc.selection.selectAll();
    artDoc.selection.copy();
    artDoc.close(SaveOptions.DONOTSAVECHANGES);

    // Back to our card document
    app.activeDocument = doc;

    // Create art layer BELOW the frame layer
    var artLayer = doc.artLayers.add();
    artLayer.name = "Art";
    artLayer.move(doc.layers[doc.layers.length - 1], ElementPlacement.PLACEAFTER);

    // Select the art layer and paste
    doc.activeLayer = artLayer;
    doc.paste();

    // The paste creates a new layer — rename it and clean up
    var pastedLayer = doc.activeLayer;
    pastedLayer.name = "Art";

    // Remove the empty layer we created (paste made its own)
    // Find and remove any layer named "Art" that is empty
    for (var i = doc.layers.length - 1; i >= 0; i--) {
        if (doc.layers[i].name === "Art" && doc.layers[i] !== pastedLayer) {
            doc.layers[i].remove();
        }
    }

    // Move the art layer below the Frame layer
    var frameLayer = null;
    for (var j = 0; j < doc.layers.length; j++) {
        if (doc.layers[j].name === "Frame") {
            frameLayer = doc.layers[j];
            break;
        }
    }
    if (frameLayer) {
        pastedLayer.move(frameLayer, ElementPlacement.PLACEAFTER);
    }

    // --- Cover-fit scale the art to the art box ------------------------------
    var bounds = pastedLayer.bounds;
    var curW = bounds[2].as("px") - bounds[0].as("px");
    var curH = bounds[3].as("px") - bounds[1].as("px");

    // Scale to cover the art box (fill, not fit)
    var scale = Math.max(artBoxW / curW, artBoxH / curH) * 100;
    pastedLayer.resize(scale, scale, AnchorPosition.MIDDLECENTER);

    // Center the art on the art box
    bounds = pastedLayer.bounds;
    var curCenterX = (bounds[0].as("px") + bounds[2].as("px")) / 2;
    var curCenterY = (bounds[1].as("px") + bounds[3].as("px")) / 2;
    var targetCenterX = artLeft + artBoxW / 2;
    var targetCenterY = artTop + artBoxH / 2;
    pastedLayer.translate(
        new UnitValue(targetCenterX - curCenterX, "px"),
        new UnitValue(targetCenterY - curCenterY, "px")
    );

    // Select the art layer so user can immediately drag it
    doc.activeLayer = pastedLayer;

    // Switch to Move Tool
    try {
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(charIDToTypeID("MovT"));
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
    } catch (e2) {
        // Move tool selection is a convenience, not critical
    }

    // Show info
    var msg = "Art swap setup complete!\n\n";
    msg += "• \"Frame\" layer = card border (on top)\n";
    msg += "• \"Art\" layer = your replacement art (underneath)\n\n";
    msg += "Drag the Art layer to adjust positioning.\n";
    msg += "When done, run ArtSwap_Export.jsx to flatten and save.";
    if (!hasSelection) {
        msg += "\n\nNote: Used standard art box. For non-standard frames,\nmake a selection around the art area BEFORE running this script.";
    }
    alert(msg);

} catch (e) {
    if (typeof e === "string" && (e === "No document open" || e === "No art file selected" || e === "Art box too small")) {
        // User-facing messages already shown
    } else {
        alert("Error: " + e);
    }
}
