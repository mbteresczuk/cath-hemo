"""
Copy annotated diagram image to macOS clipboard for pasting into Epic.
"""
import io
import os
import subprocess
import tempfile
from PIL import Image


def copy_image_to_clipboard(img: Image.Image) -> tuple:
    """
    Copy PIL image to clipboard using macOS osascript.
    Returns (success: bool, message: str).
    """
    try:
        # Save to temp PNG file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            img.save(tmp_path, format="PNG")

        # Use osascript to copy image to clipboard
        script = f'''
        set imgFile to POSIX file "{tmp_path}"
        set imgAlias to imgFile as alias
        tell application "Finder"
            open imgAlias
        end tell
        delay 0.5
        tell application "Preview"
            activate
            set frontDoc to front document
            tell application "System Events"
                keystroke "a" using command down
                keystroke "c" using command down
            end tell
        end tell
        '''

        # Alternative: use pbcopy-compatible approach via tiff
        # More reliable: convert to TIFF and use pbcopy
        with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as tmp2:
            tmp_tiff = tmp2.name
            img.save(tmp_tiff, format="TIFF")

        result = subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{tmp_tiff}") as TIFF picture)'],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Cleanup
        os.unlink(tmp_path)
        os.unlink(tmp_tiff)

        if result.returncode == 0:
            return True, "Image copied to clipboard. Paste with Cmd+V in Epic."
        else:
            return False, f"Clipboard copy failed: {result.stderr.strip()}"

    except Exception as e:
        return False, f"Could not copy to clipboard: {str(e)}"


def get_clipboard_help() -> str:
    return (
        "To use the diagram in Epic:\n"
        "1. Download the PNG using the Download button below\n"
        "2. Open the downloaded file\n"
        "3. Press Cmd+A then Cmd+C to copy\n"
        "4. Paste into your Epic note with Cmd+V"
    )
