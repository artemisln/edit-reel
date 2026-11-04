#!/usr/bin/env python3
"""
Fullscreen product-demo capture: Playwright drives Chrome, we record it ourselves.

No Claude-in-Chrome extension, so there is no orange outline and no glowing cursor.
Fullscreen, so there is no Dock, no macOS menu bar, no tabs and no address bar.

macOS only (AppleScript fullscreen + ffmpeg avfoundation screen capture). The terminal running
this needs Screen Recording and Accessibility permission in System Settings > Privacy & Security.

Usage:
    python3 capture.py beats_file.py            # beats_file defines BEATS + START_URL

Edit BEATS in your per-product file. Keep the whole run under 90 seconds.

Environment overrides:
    REEL_PROFILE_DIR   Chrome profile used for recording
                       (default ~/Library/Application Support/ReelRecordingProfile)
    REEL_CAPTURE_DIR   where the videos go (default ./demo_captures)
    REEL_SCREEN        avfoundation screen number to record (default: the first screen)
"""
import json, os, pathlib, re, subprocess, sys, time, importlib.util

HOME = pathlib.Path.home()
PROFILE = pathlib.Path(os.environ.get(
    "REEL_PROFILE_DIR", HOME / "Library/Application Support/ReelRecordingProfile"))
OUTDIR = pathlib.Path(os.environ.get("REEL_CAPTURE_DIR", "demo_captures")).resolve()
FPS = 30


# ---------------------------------------------------------------- profile setup
def prepare_profile():
    """One-time-ish prefs so the browser records clean. Safe to run every time."""
    prefs = PROFILE / "Default/Preferences"
    if not prefs.exists():
        return "profile not created yet, will apply on next run"
    d = json.loads(prefs.read_text())
    b = d.setdefault("browser", {})
    # THE key setting: without this the toolbar stays pinned in fullscreen
    b["show_fullscreen_toolbar"] = False
    # kill the auto-assigned profile theme tint on the frame
    b["theme"] = {"follows_system_colors": True}
    prefs.write_text(json.dumps(d))
    return "prefs applied"


def screen_index():
    """The avfoundation device index SHIFTS between runs (cameras come and go). Always re-query it."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation",
                        "-list_devices", "true", "-i", ""], capture_output=True, text=True)
    screens = re.findall(r"\[(\d+)\] Capture screen (\d+)", r.stderr)
    if not screens:
        sys.exit("no 'Capture screen' device found. Does the terminal have Screen Recording permission?")
    want = os.environ.get("REEL_SCREEN")
    for idx, num in screens:
        if want is None or num == want:
            return idx
    sys.exit(f"screen {want} not found, available: {screens}")


def start_recording(idx, raw):
    """Record the screen with ffmpeg. Stopped by sending 'q' on stdin."""
    return subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation",
         "-framerate", str(FPS), "-capture_cursor", "1", "-i", f"{idx}:none",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
         str(raw)],
        stdin=subprocess.PIPE)


def stop_recording(proc, raw):
    try:
        proc.communicate(b"q", timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(raw)], capture_output=True, text=True)
    try:
        return float(r.stdout)
    except ValueError:
        return None


def go_fullscreen():
    """macOS fullscreen. This is what removes the Dock and the menu bar."""
    subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'],
                   capture_output=True)
    time.sleep(0.6)
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "f" '
                    'using {command down, control down}'], capture_output=True)
    time.sleep(2.5)   # let the fullscreen animation and the "press esc" toast finish


# ---------------------------------------------------------------- beat helpers
class Stage:
    """Passed to each beat. Use these, not raw playwright, so pacing stays consistent."""
    def __init__(self, page):
        self.page = page

    def glide_to(self, selector, steps=30):
        el = self.page.wait_for_selector(selector, timeout=15000)
        bb = el.bounding_box()
        self.page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, steps=steps)
        self.page.wait_for_timeout(250)
        return el

    def click(self, selector):
        el = self.glide_to(selector)
        el.click()
        self.page.wait_for_timeout(400)

    def type(self, text, delay=65):
        """Character-by-character. Instant text reads as a paste and looks fake."""
        self.page.keyboard.type(text, delay=delay)
        self.page.wait_for_timeout(500)

    def press(self, key):
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(400)

    def scroll(self, dy=500):
        self.page.mouse.wheel(0, dy)
        self.page.wait_for_timeout(900)

    def hold(self, seconds=2.5):
        """Sit on an end state long enough to be cuttable. Do this on every beat."""
        self.page.wait_for_timeout(int(seconds * 1000))

    def goto(self, url):
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.page.wait_for_timeout(1500)


# ---------------------------------------------------------------- main
def run(beats_module):
    from playwright.sync_api import sync_playwright

    OUTDIR.mkdir(parents=True, exist_ok=True)
    name = getattr(beats_module, "NAME", "capture")
    raw = OUTDIR / f"{name}_raw.mp4"
    out = OUTDIR / f"{name}.mp4"

    print(prepare_profile())

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="chrome", headless=False, viewport=None,
            ignore_default_args=["--enable-automation"],   # kills the automation infobar
            args=["--window-position=0,0",
                  "--test-type",                            # kills "unsupported flag" bar
                  "--hide-crash-restore-bubble", "--disable-session-crashed-bubble",
                  "--no-default-browser-check", "--no-first-run"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        st = Stage(page)

        # settle on the start URL BEFORE recording so nothing ugly is in frame
        st.goto(getattr(beats_module, "START_URL", "about:blank"))
        prepare_profile()          # ensure prefs exist now the profile is created
        go_fullscreen()

        geom = page.evaluate(
            "()=>({w:innerWidth,h:innerHeight,x:screenX,y:screenY,sw:screen.width})")
        print("viewport:", geom)

        idx = screen_index()
        rec = start_recording(idx, raw)
        time.sleep(1.8)

        try:
            for i, beat in enumerate(beats_module.BEATS, 1):
                label = getattr(beat, "__doc__", None) or beat.__name__
                print(f"  beat {i}: {label.strip()}")
                beat(st)
        finally:
            time.sleep(0.8)
            dur = stop_recording(rec, raw)
            print("raw duration:", dur)
            ctx.close()

    if dur and dur > 90:
        print(f"WARNING: {dur:.0f}s exceeds the 90s cap. Trim the beat list.")

    crop_to_content(raw, out, geom)
    return out


def crop_to_content(raw, out, geom):
    """Fullscreen leaves a black band where the window did not fill the screen."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw)],
        capture_output=True, text=True).stdout.strip()
    CW, CH = [int(x) for x in probe.split(",")[:2]]
    scale = CW / geom["sw"]                     # logical -> pixels, 2.0 on a Retina screen
    # use the REAL window position, do not assume it is centred or bottom aligned
    w = min(int(geom["w"] * scale), CW)
    h = min(int(geom["h"] * scale), CH)
    x = max(0, min(int(geom.get("x", 0) * scale), CW - w))
    y = max(0, min(int(geom.get("y", 0) * scale), CH - h))
    print(f"capture {CW}x{CH} scale {scale} -> crop {w}x{h}+{x}+{y}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-vf", f"crop={w}:{h}:{x}:{y}",
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast", str(out)], check=True)
    print("clean capture ->", out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python3 capture.py <beats_file.py>")
    path = pathlib.Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("beats", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run(mod)
