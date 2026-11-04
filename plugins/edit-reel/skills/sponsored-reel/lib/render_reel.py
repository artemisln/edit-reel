"""Pill captions with a glowing hook title, for a sponsored reel.

Body captions are white on a translucent black pill. The opening hook title is
white upright caps over gold italic caps, each word glowing in its own colour and
appearing only once it is spoken.

Usage:
    python3 render_reel.py <project-dir>

Expects <project>/work/recut_v2.mp4 (from recut.py) and <project>/work/vo.json
(Whisper output with word_timestamps=True). Edit SCREENS for your own hook.
See ../SKILL.md.
"""
import json, subprocess, sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fonts import find_font

PROJECT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

SRC = f"{PROJECT}/work/recut_v2.mp4"
OUT = f"{PROJECT}/edited/sponsored_reel_captioned.mp4"
VO = f"{PROJECT}/work/vo.json"

W, H, FPS = 1080, 1920, 30

# Fonts: Manrope Bold for body captions, Inter Display Black + Black Italic for the
# hook, any serif italic for the tail line (Georgia Italic ships with macOS and
# Windows; Noto Serif Italic is a free alternative that also covers Greek).
F_SUB = find_font("FONT_SUB", "Manrope-Bold.otf", "Manrope-Bold.ttf", project=PROJECT)
F_HOOK = find_font("FONT_HOOK", "InterDisplay-Black.otf", "InterDisplay-Black.ttf", project=PROJECT)
F_HOOK_I = find_font("FONT_HOOK_ITALIC", "InterDisplay-BlackItalic.otf",
                     "InterDisplay-BlackItalic.ttf", project=PROJECT)
F_SERIF = find_font("FONT_SERIF", "Georgia Italic.ttf", "georgiai.ttf",
                    "NotoSerif-Italic.ttf", project=PROJECT)

SUB_SIZE, SUB_Y = 58, 0.20
LINE_SP = 12
PILL_PADX, PILL_PADY, PILL_R = 26, 16, 22
PILL_ALPHA = 150                      # translucent black
MAX_W = int(W * 0.78)

HOOK_SIZE, ACCENT_SIZE, HOOK_STROKE = 84, 104, 12
HOOK_Y, HOOK_LINE_H = 0.235, 122
HOOK_MAX_W = int(W * 0.72)

GOLD = (245, 192, 19)      # sampled off the reference look, not guessed
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# Whisper mishearings to fix. Text only, timings untouched.
FIXES = [("clod", "Claude"), ("lightning", "lighting")]
HOOK_END = 2.95

# The title is built as screens, each a white upright line with a gold italic line
# under it. No outline anywhere; every letter carries a glow in its own colour.
# Each word is (text, the second it is spoken). Example hook for a game-builder demo.
SCREENS = [
    {"start": 0.00, "end": 1.44, "lines": [
        {"style": "w_sans", "words": [("HOW", 0.00), ("TO", 0.36), ("BUILD", 0.56)]},
        {"style": "g_sans", "words": [("THE", 0.78), ("VIDEO", 1.02), ("GAME", 1.30)]}]},
    {"start": 1.44, "end": 2.08, "lines": [
        {"style": "w_sans", "words": [("OF", 1.44), ("YOUR", 1.64)]},
        {"style": "g_sans", "words": [("DREAMS", 1.86)]}]},
    {"start": 2.08, "end": HOOK_END, "lines": [
        {"style": "w_serif", "words": [("In", 2.08)]},
        {"style": "g_serif", "words": [("2", 2.28), ("minutes", 2.50)]}]},
]

GLOW_BLUR, GLOW_ALPHA = 9, 0.85     # tight halo, not a big haze
FADE_IN, FADE_BLUR = 0.13, 14       # each word resolves from a blur, nothing before its time


def load_words():
    r = json.load(open(VO))
    out = []
    for s in r["segments"]:
        for w in s["words"]:
            t = w["word"].strip()
            for a, b in FIXES:
                if t.lower().strip(".,") == a:
                    t = b + t[len(a):] if len(t) > len(a) else b
            if t.startswith(".") and out:
                out[-1]["word"] += t
                out[-1]["end"] = w["end"]
                continue
            out.append({"word": t, "start": w["start"], "end": w["end"]})
    return out


def wrap_text(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def group_captions(words, max_words=5):
    """Split on sentence ends, then into balanced chunks with no orphan tails."""
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if w["word"].endswith((".", "!", "?")):
            sents.append(cur); cur = []
    if cur:
        sents.append(cur)

    out = []
    for s in sents:
        n = len(s)
        k = max(1, round(n / max_words))
        size = -(-n // k)
        chunks = [s[i:i + size] for i in range(0, n, size)]
        if len(chunks) > 1 and len(chunks[-1]) <= 2:
            chunks[-2].extend(chunks.pop())
        for c in chunks:
            out.append({"text": " ".join(x["word"] for x in c),
                        "start": c[0]["start"], "end": c[-1]["end"]})
    for i in range(len(out) - 1):
        out[i]["end"] = out[i + 1]["start"]
    return out


def hook_fonts():
    return {
        "w_sans":  (ImageFont.truetype(F_HOOK,  HOOK_SIZE),   WHITE),
        "g_sans":  (ImageFont.truetype(F_HOOK_I, HOOK_SIZE),   GOLD),
        "w_serif": (ImageFont.truetype(F_SERIF, ACCENT_SIZE), WHITE),
        "g_serif": (ImageFont.truetype(F_SERIF, ACCENT_SIZE), GOLD),
    }


def layout_screens(d0, fonts):
    for sc in SCREENS:
        n = len(sc["lines"])
        y0 = int(H * HOOK_Y) - (n - 1) * HOOK_LINE_H // 2
        for li, line in enumerate(sc["lines"]):
            font, col = fonts[line["style"]]
            sp = d0.textlength(" ", font=font)
            widths = [d0.textlength(w, font=font) for w, _ in line["words"]]
            total = sum(widths) + sp * (len(widths) - 1)
            x = W / 2 - total / 2
            placed = []
            for (word, ts), wd in zip(line["words"], widths):
                placed.append({"text": word, "t": ts, "x": x, "y": y0 + li * HOOK_LINE_H,
                               "font": font, "col": col})
                x += wd + sp
            line["placed"] = placed
    return SCREENS


def draw_hook(img, screen, t):
    """Words appear only once spoken, resolving out of a short blur. No outline,
    just a tight halo in each word's own colour."""
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    crisp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    soft = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd, cd, sd = (ImageDraw.Draw(x) for x in (glow, crisp, soft))
    softest = 0.0

    for line in screen["lines"]:
        for w in line["placed"]:
            age = t - w["t"]
            if age < 0:
                continue                       # not said yet, draw nothing at all
            if age < FADE_IN:
                p = age / FADE_IN
                sd.text((w["x"], w["y"]), w["text"], font=w["font"],
                        fill=w["col"] + (int(255 * p),), anchor="ls")
                softest = max(softest, 1 - p)
            else:
                gd.text((w["x"], w["y"]), w["text"], font=w["font"],
                        fill=w["col"] + (255,), anchor="ls")
                cd.text((w["x"], w["y"]), w["text"], font=w["font"],
                        fill=w["col"] + (255,), anchor="ls")

    g = glow.filter(ImageFilter.GaussianBlur(GLOW_BLUR))
    g.putalpha(g.getchannel("A").point(lambda a: int(a * GLOW_ALPHA)))
    img.alpha_composite(g)
    if softest > 0:
        img.alpha_composite(soft.filter(ImageFilter.GaussianBlur(FADE_BLUR * softest)))
    img.alpha_composite(crisp)


def draw_caption(img, lines, font, d0):
    lh = SUB_SIZE + LINE_SP
    widths = [d0.textlength(ln, font=font) for ln in lines]
    box_w = max(widths) + PILL_PADX * 2
    box_h = len(lines) * lh + PILL_PADY * 2
    x0 = W / 2 - box_w / 2
    y0 = int(H * SUB_Y) - box_h / 2

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [x0, y0, x0 + box_w, y0 + box_h], radius=PILL_R, fill=(0, 0, 0, PILL_ALPHA))
    img.alpha_composite(layer)

    d = ImageDraw.Draw(img)
    for j, ln in enumerate(lines):
        d.text((W / 2 - widths[j] / 2, y0 + PILL_PADY + j * lh), ln,
               font=font, fill=WHITE + (255,))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    words = load_words()
    f_sub = ImageFont.truetype(F_SUB, SUB_SIZE)
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    screens = layout_screens(d0, hook_fonts())
    caps = group_captions([w for w in words if w["start"] >= HOOK_END], max_words=5)
    for c in caps:
        c["lines"] = wrap_text(d0, c["text"], f_sub, MAX_W)

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", SRC],
        capture_output=True, text=True).stdout.strip())
    n = int(dur * FPS)

    dec = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", SRC, "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", SRC,
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", OUT], stdin=subprocess.PIPE)

    fsize = W * H * 3
    for i in range(n):
        raw = dec.stdout.read(fsize)
        if len(raw) < fsize:
            break
        t = i / FPS
        img = Image.frombytes("RGB", (W, H), raw).convert("RGBA")

        sc = next((x for x in screens if x["start"] <= t < x["end"]), None)
        if sc:
            draw_hook(img, sc, t)
        else:
            cap = next((c for c in caps if c["start"] <= t < c["end"]), None)
            if cap:
                draw_caption(img, cap["lines"], f_sub, d0)

        enc.stdin.write(img.convert("RGB").tobytes())

    enc.stdin.close(); dec.stdout.close()
    enc.wait(); dec.wait()
    print("DONE ->", OUT)


if __name__ == "__main__":
    main()
