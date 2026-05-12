"""Build script — packages MTG Deck Imager into a standalone .exe."""
import PyInstaller.__main__
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
main_script = os.path.join(script_dir, "mtg_deck_imager.py")

PyInstaller.__main__.run([
    main_script,
    "--onefile",
    "--windowed",
    "--name=MTGDeckImager",
    "--clean",
    f"--distpath={os.path.join(script_dir, 'dist')}",
    f"--workpath={os.path.join(script_dir, 'build')}",
    f"--specpath={script_dir}",
])
