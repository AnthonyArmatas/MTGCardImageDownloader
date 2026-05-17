// =============================================================================
// ArtSwap_BatchExport.jsx — Export all open proxy cards
// =============================================================================
//
// Run this AFTER ArtSwap_BatchSetup.jsx and repositioning art in each document.
// Flattens and saves each document that has Frame+Art layers.
// Saves as "<original_name>_proxy.png" in the same folder as the original.
// =============================================================================

#target photoshop

app.preferences.rulerUnits = Units.PIXELS;

try {
    if (app.documents.length === 0) {
        alert("No documents open.");
        throw "No documents";
    }

    // Ask for output folder
    var outputFolder = Folder.selectDialog("Select output folder for proxy PNGs");
    if (!outputFolder) throw "Cancelled";

    var exported = 0;
    var skipped = 0;
    var errors = 0;

    // Process all open documents
    // Work backwards since closing documents shifts indices
    var totalDocs = app.documents.length;
    for (var i = totalDocs - 1; i >= 0; i--) {
        app.activeDocument = app.documents[i];
        var doc = app.activeDocument;

        // Check for Frame+Art layer structure
        var hasFrame = false;
        var hasArt = false;
        for (var j = 0; j < doc.layers.length; j++) {
            if (doc.layers[j].name === "Frame") hasFrame = true;
            if (doc.layers[j].name === "Art") hasArt = true;
        }

        if (!hasFrame || !hasArt) {
            skipped++;
            continue;
        }

        try {
            var baseName = doc.name.replace(/\.[^.]+$/, "");
            var outputFile = new File(outputFolder + "/" + baseName + "_proxy.png");

            // Flatten
            doc.flatten();

            // Save as PNG
            var pngOpts = new PNGSaveOptions();
            pngOpts.compression = 6;
            pngOpts.interlaced = false;
            doc.saveAs(outputFile, pngOpts, true, Extension.LOWERCASE);

            // Close without saving the PSD (we already saved the PNG)
            doc.close(SaveOptions.DONOTSAVECHANGES);

            exported++;
        } catch (err) {
            errors++;
            $.writeln("Error exporting " + doc.name + ": " + err);
        }
    }

    var msg = "Batch export complete!\n\n";
    msg += "Exported: " + exported + "\n";
    if (skipped > 0) msg += "Skipped (no Frame+Art layers): " + skipped + "\n";
    if (errors > 0) msg += "Errors: " + errors + "\n";
    msg += "\nOutput folder: " + outputFolder.fsName;
    alert(msg);

} catch (e) {
    if (typeof e === "string" && (e === "No documents" || e === "Cancelled")) {
        // Already handled
    } else {
        alert("Error: " + e);
    }
}
