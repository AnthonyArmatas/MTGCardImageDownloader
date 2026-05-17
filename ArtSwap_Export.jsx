// =============================================================================
// ArtSwap_Export.jsx — Photoshop ExtendScript: Export the finished proxy card
// =============================================================================
//
// Run this AFTER ArtSwap_Setup.jsx and positioning the art.
// Flattens all layers and saves as PNG next to the original file.
//
// If run on a single card: saves as "<original_name>_proxy.png"
// If run in batch mode: processes all open documents with Frame+Art layers
// =============================================================================

#target photoshop

app.preferences.rulerUnits = Units.PIXELS;

try {
    if (app.documents.length === 0) {
        alert("No documents open.");
        throw "No document open";
    }

    var doc = app.activeDocument;
    var exported = 0;

    // Check if this document has our Frame+Art layer structure
    var hasFrame = false;
    var hasArt = false;
    for (var i = 0; i < doc.layers.length; i++) {
        if (doc.layers[i].name === "Frame") hasFrame = true;
        if (doc.layers[i].name === "Art") hasArt = true;
    }

    if (!hasFrame || !hasArt) {
        alert("This document doesn't have Frame + Art layers.\nRun ArtSwap_Setup.jsx first.");
        throw "Missing layers";
    }

    // Determine output path
    var outputPath;
    var docPath;
    try {
        docPath = doc.path;
    } catch (e) {
        docPath = Folder.desktop;
    }

    // Build output filename
    var baseName = doc.name.replace(/\.[^.]+$/, "");  // strip extension
    var outputFile = new File(docPath + "/" + baseName + "_proxy.png");

    // If file exists, ask to overwrite
    if (outputFile.exists) {
        var overwrite = confirm("File already exists:\n" + outputFile.fsName + "\n\nOverwrite?");
        if (!overwrite) {
            throw "Cancelled";
        }
    }

    // Flatten
    doc.flatten();

    // Save as PNG
    var pngOpts = new PNGSaveOptions();
    pngOpts.compression = 6;
    pngOpts.interlaced = false;
    doc.saveAs(outputFile, pngOpts, true, Extension.LOWERCASE);
    exported++;

    alert("Exported: " + outputFile.fsName);

} catch (e) {
    if (typeof e === "string" && (e === "No document open" || e === "Missing layers" || e === "Cancelled")) {
        // Already handled
    } else {
        alert("Error: " + e);
    }
}
