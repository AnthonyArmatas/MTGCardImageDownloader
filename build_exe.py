"""Build script — packages MTG Deck Imager into a standalone .exe."""
import PyInstaller.__main__
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
main_script = os.path.join(script_dir, "mtg_deck_imager.py")
jsx_file = os.path.join(script_dir, "CreateSheet.jsx")

# Include CreateSheet.jsx as a data file so Photoshop COM mode works from the exe
add_data = f"{jsx_file};."

PyInstaller.__main__.run([
    main_script,
    "--onefile",
    "--windowed",
    "--name=MTGDeckImager",
    "--clean",
    f"--add-data={add_data}",
    f"--distpath={os.path.join(script_dir, 'dist')}",
    f"--workpath={os.path.join(script_dir, 'build')}",
    f"--specpath={script_dir}",
])
