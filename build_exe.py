"""Build script — packages MTG Deck Imager into a standalone .exe."""
import PyInstaller.__main__
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
main_script = os.path.join(script_dir, "mtg_deck_imager.py")
jsx_files = [
    os.path.join(script_dir, "CreateSheet.jsx"),
    os.path.join(script_dir, "ArtSwap_Setup.jsx"),
    os.path.join(script_dir, "ArtSwap_Export.jsx"),
    os.path.join(script_dir, "ArtSwap_BatchSetup.jsx"),
    os.path.join(script_dir, "ArtSwap_BatchExport.jsx"),
]

# Build --add-data args for each JSX file
add_data_args = []
for jsx in jsx_files:
    add_data_args.extend([f"--add-data={jsx};."])

PyInstaller.__main__.run([
    main_script,
    "--onefile",
    "--windowed",
    "--name=MTGDeckImager",
    "--clean",
    *add_data_args,
    f"--distpath={os.path.join(script_dir, 'dist')}",
    f"--workpath={os.path.join(script_dir, 'build')}",
    f"--specpath={script_dir}",
])
