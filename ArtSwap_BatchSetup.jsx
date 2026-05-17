// =============================================================================
// ArtSwap_BatchSetup.jsx — Set up multiple cards for art replacement at once
// =============================================================================
//
// Usage:
//   1. Run this script (no documents need to be open)
//   2. Pick a folder of card images
//   3. Pick a folder of replacement art images
//   4. Cards and art are paired by alphabetical sort order
//   5. Each pair opens as a document with Frame + Art layers ready to adjust
//   6. Go through each open document, reposition the art with Move tool
//   7. Run ArtSwap_BatchExport.jsx when all cards look right
//
// =============================================================================

#target photoshop

app.preferences.rulerUnits = Units.PIXELS;

// Standard art box ratios (same as ArtSwap_Setup.jsx)
var STD_ART_LEFT   = 0.065;
var STD_ART_TOP    = 0.112;
var STD_ART_RIGHT  = 0.935;
var STD_ART_BOTTOM = 0.555;

var IMAGE_EXTENSIONS = /\.(png|jpg|jpeg|tif|tiff|bmp)$/i;

function getImageFiles(folder) {
    var files = folder.getFiles();
    var images = [];
    for (var i = 0; i < files.length; i++) {
        if (files[i] instanceof File && IMAGE_EXTENSIONS.test(files[i].name)) {
            images.push(files[i]);
        }
    }
    images.sort(function(a, b) {
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
    return images;
}

try {
    // Pick folders
    var cardFolder = Folder.selectDialog("Select folder of CARD images");
    if (!cardFolder) throw "Cancelled";

    var artFolder = Folder.selectDialog("Select folder of REPLACEMENT ART images");
    if (!artFolder) throw "Cancelled";

    var cardFiles = getImageFiles(cardFolder);
    var artFiles = getImageFiles(artFolder);

    if (cardFiles.length === 0) {
        alert("No image files found in the card folder.");
        throw "No cards";
    }
    if (artFiles.length === 0) {
        alert("No image files found in the art folder.");
        throw "No art";
    }

    var pairCount = Math.min(cardFiles.length, artFiles.length);
    if (cardFiles.length !== artFiles.length) {
        var proceed = confirm(
            "Card images: " + cardFiles.length + "\nArt images: " + artFiles.length +
            "\n\nCounts differ — will process " + pairCount + " pairs.\nContinue?"
        );
        if (!proceed) throw "Cancelled";
    }

    // Process each pair
    for (var idx = 0; idx < pairCount; idx++) {
        var cardFile = cardFiles[idx];
        var artFile = artFiles[idx];

        // Open card
        var doc = app.open(cardFile);
        var cardW = doc.width.as("px");
        var cardH = doc.height.as("px");

        // Calculate art box from standard ratios
        var artLeft   = Math.round(cardW * STD_ART_LEFT);
        var artTop    = Math.round(cardH * STD_ART_TOP);
        var artRight  = Math.round(cardW * STD_ART_RIGHT);
        var artBottom = Math.round(cardH * STD_ART_BOTTOM);
        var artBoxW = artRight - artLeft;
        var artBoxH = artBottom - artTop;

        // Flatten and prepare frame
        doc.flatten();
        doc.activeLayer.name = "Frame";
        doc.activeLayer.isBackgroundLayer = false;

        // Cut out art area
        var selRegion = [
            [artLeft, artTop],
            [artRight, artTop],
            [artRight, artBottom],
            [artLeft, artBottom]
        ];
        doc.selection.select(selRegion);
        doc.selection.clear();
        doc.selection.deselect();

        // Open art, copy, close
        var artDoc = app.open(artFile);
        artDoc.flatten();
        artDoc.selection.selectAll();
        artDoc.selection.copy();
        artDoc.close(SaveOptions.DONOTSAVECHANGES);

        // Back to card
        app.activeDocument = doc;

        // Paste art
        doc.paste();
        var pastedLayer = doc.activeLayer;
        pastedLayer.name = "Art";

        // Move art layer below frame
        var frameLayer = doc.layers[0].name === "Frame" ? doc.layers[0] : null;
        if (!frameLayer) {
            for (var j = 0; j < doc.layers.length; j++) {
                if (doc.layers[j].name === "Frame") { frameLayer = doc.layers[j]; break; }
            }
        }
        if (frameLayer) {
            pastedLayer.move(frameLayer, ElementPlacement.PLACEAFTER);
        }

        // Cover-fit scale
        var bounds = pastedLayer.bounds;
        var curW = bounds[2].as("px") - bounds[0].as("px");
        var curH = bounds[3].as("px") - bounds[1].as("px");
        var scale = Math.max(artBoxW / curW, artBoxH / curH) * 100;
        pastedLayer.resize(scale, scale, AnchorPosition.MIDDLECENTER);

        // Center on art box
        bounds = pastedLayer.bounds;
        var curCenterX = (bounds[0].as("px") + bounds[2].as("px")) / 2;
        var curCenterY = (bounds[1].as("px") + bounds[3].as("px")) / 2;
        var targetCenterX = artLeft + artBoxW / 2;
        var targetCenterY = artTop + artBoxH / 2;
        pastedLayer.translate(
            new UnitValue(targetCenterX - curCenterX, "px"),
            new UnitValue(targetCenterY - curCenterY, "px")
        );

        // Select art layer for positioning
        doc.activeLayer = pastedLayer;
    }

    alert(
        "Batch setup complete!\n\n" +
        pairCount + " card(s) prepared.\n\n" +
        "Go through each open document and reposition the art layer.\n" +
        "When done, run ArtSwap_BatchExport.jsx to flatten and save all."
    );

} catch (e) {
    if (typeof e === "string" && (e === "Cancelled" || e === "No cards" || e === "No art")) {
        // Already handled
    } else {
        alert("Error: " + e);
    }
}
