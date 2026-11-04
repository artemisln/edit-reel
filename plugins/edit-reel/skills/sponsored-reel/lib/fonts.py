"""Locate font files without hardcoding a machine-specific path.

Lookup order for each font:
  1. An environment variable (for example FONT_SUB=/path/to/Manrope-Bold.ttf)
  2. A fonts/ folder in the project directory
  3. The usual system and user font folders on macOS, Linux and Windows

Pass several candidate file names; the first one found wins.
"""
import glob
import os

FONT_DIRS = [
    "fonts",
    os.path.expanduser("~/Library/Fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
]


def find_font(env_var, *names, project=None):
    """Return the path of the first font file matching one of `names`."""
    override = os.environ.get(env_var)
    if override and os.path.exists(override):
        return override
    dirs = ([os.path.join(project, "fonts")] if project else []) + FONT_DIRS
    for name in names:
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            direct = os.path.join(d, name)
            if os.path.exists(direct):
                return direct
            hits = glob.glob(os.path.join(d, "**", name), recursive=True)
            if hits:
                return hits[0]
    raise FileNotFoundError(
        f"Font not found: tried {', '.join(names)}. Install it, drop it in <project>/fonts/, "
        f"or set {env_var}=/path/to/font.")
