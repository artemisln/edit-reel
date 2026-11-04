"""Bilingual captions: a native-language line with a smaller English translation
underneath, plus static punch-ins, pop-in overlays, chat bubbles and a measured SFX mix.

Usage:
    python3 render_bilingual.py <project-dir>

Expects <project>/edited/voiceover_with_clips.mp4 and <project>/work/vo.json
(Whisper output with word_timestamps=True). Fill BILINGUAL, PUNCHES, OVERLAYS,
BUBBLES and SFX for your video; the values below are a Greek example.
See ../SKILL.md.
"""
import json, re, subprocess, sys, os
from PIL import Image, ImageDraw, ImageFont
from fonts import find_font

PROJECT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

SRC = f"{PROJECT}/edited/voiceover_with_clips.mp4"
TMP = f"{PROJECT}/work/_video_only.mp4"
OUT = f"{PROJECT}/edited/sponsored_reel_bilingual.mp4"
VO = f"{PROJECT}/work/vo.json"

W, H, FPS = 1080, 1920, 30
# Fonts: Manrope Bold for captions (covers Greek), Inter Display Black for the hook.
# The accent font must contain Greek glyphs if you caption in Greek (Didot does not).
FONT = find_font("FONT_SUB", "Manrope-Bold.otf", "Manrope-Bold.ttf", project=PROJECT)
F_TITLE = find_font("FONT_HOOK", "InterDisplay-Black.otf", "InterDisplay-Black.ttf", project=PROJECT)

EL_SIZE, EL_STROKE = 60, 8          # native-language line
EN_SIZE, EN_STROKE = 40, 6          # English line underneath
SUB_Y = 0.735
LINE_SP, GAP = 12, 16
MAX_W = int(W * 0.86)

WHITE, BLACK = (255, 255, 255), (0, 0, 0)
EN_GREY = (214, 214, 214)

TALKING_END = 21.83

# Whisper slips. Text only, timing untouched. Map the exact token to its fix.
FIXES = {
    "Meetups": "meetups", "Tech.": "tech;", "ρελιστικό.": "ρεαλιστικό.",
    "βεβαιότητα": "αβεβαιότητα", "πρωτού": "προτού", "κάν": "καν",
}

# (start, end, native line, English line), cut to the word timings.
# Drop the English (empty string) on sections where a UI fills the frame.
BILINGUAL = [
    (0.00,  1.66, "Πάω σε meetups κάθε βδομάδα",            "I go to meetups every week"),
    (1.66,  3.40, "και ακούω συνέχεια την ίδια ερώτηση.",   "and I keep hearing the same question."),
    (3.40,  4.92, "Πώς θα βρω την πρώτη μου δουλειά στο tech;", "How do I get my first job in tech?"),
    (4.92,  6.54, "Και η αλήθεια είναι ότι οι περισσότεροι", "And the truth is that most of them"),
    (6.54,  8.16, "δεν έχουν θέμα με τις δεξιότητες.",      "don't have a skills problem."),
    (8.16,  9.60, "Έχουν πρόβλημα όμως με το ότι",          "What they do have is that"),
    (9.60, 11.80, "δεν ξέρουν τι να ζητήσουν και τι είναι ρεαλιστικό.", "they don't know what to ask for, or what's realistic."),
    (11.80, 13.26, "Δεν ξέρουν τι μισθό να ζητήσουν,",      "They don't know what salary to ask for,"),
    (13.26, 15.22, "δεν ξέρουν ποιες εταιρείες παίρνουν juniors,", "which companies actually hire juniors,"),
    (15.22, 16.28, "δεν ξέρουν αν είναι έτοιμοι",           "or whether they're even ready."),
    (16.28, 18.44, "και όλη αυτή η αβεβαιότητα τους κρατάει πίσω", "And all that uncertainty holds them back"),
    (18.44, 19.90, "περισσότερο από ό,τι το βιογραφικό τους.", "more than their CV ever does."),
    (19.90, 21.83, "Γι' αυτό τους δείχνω αυτό το εργαλείο.", "So now I show them this tool."),
    (21.92, 24.26, "Φιλτράρεις entry level θέσεις, είτε remote,", "You filter entry level jobs, remote"),
    (24.26, 26.84, "είτε από κοντά σε όποια πόλη θες",      "or on-site in any city you want"),
    (26.84, 28.22, "και κάνεις την αίτησή σου επί τόπου.",  "and you apply right there."),
]

# Static punch-ins: (start, end, zoom). Hard cut in, hard cut out, no ramp.
PUNCHES = [
    (0.00,  3.40, 1.12),   # the hook, tighter framing
    (11.80, 15.22, 1.08),  # the list of "they don't know"
    (19.90, 21.83, 1.10),  # the turn to the product
]

GOLD = (244, 186, 74)

# The hook is carried by the subtitle itself, set in a heavier face, not by a
# second block of text saying the same thing.
HOOK_STYLE_END = 4.92
HOOK_SIZE, HOOK_STROKE = 70, 10

AST = f"{PROJECT}/work/assets"
# (path, start, end, x centre, y centre, max size px). Leave empty for none.
OVERLAYS = [
    # (f"{AST}/event.png",  0.60,  3.30, 0.655, 0.170, 470),
    # (f"{AST}/js.png",     6.95,  8.10, 0.215, 0.130, 130),   # a row of logos, staggered 0.1s
    # (f"{AST}/python.png", 7.05,  8.10, 0.405, 0.130, 130),
    # (f"{AST}/cv.png",     19.00, 19.88, 0.700, 0.195, 330),
    # (f"{AST}/product_logo.png", 19.95, 21.45, 0.700, 0.185, 260),
]

BUB = f"{PROJECT}/work/bubbles"
# Styled text bubbles, never real DM screenshots. (path, appear, x centre, y centre);
# all clear together at BUB_END. Leave empty for none.
BUBBLES = [
    # (f"{BUB}/b1.png", 11.95, 0.30, 0.095),
    # (f"{BUB}/b2.png", 13.40, 0.66, 0.170),
    # (f"{BUB}/b3.png", 15.35, 0.28, 0.245),
    # (f"{BUB}/b4.png", 15.95, 0.70, 0.320),
]
BUB_END = 18.70   # all bubbles clear before the next overlay appears
BUB_MAX_W = int(1080 * 0.52)

# SFX: a project audios/ folder next to the video wins, else the shared pack that
# ships with the edit-reel skill.
_SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "edit-reel", "audios")
LIB = f"{PROJECT}/audios" if os.path.isdir(f"{PROJECT}/audios") else os.path.normpath(_SHARED)

# (at, path, clip_start, clip_len, target_dB). clip_start skips any leading silence
# in the source file (find it with silencedetect); the gain needed to hit target_dB
# is measured at render time. With a VO around -18 dB RMS: transients about -22 dB,
# beds about -28 dB, the opening riser -26 dB. Never the same file twice.
SFX = [
    (0.15,  f"{LIB}/trimmed_riser.mp3",  0.00, 2.30, -26),  # opening title
    (21.83, f"{LIB}/trimmed_whoosh.mp3", 0.00, 0.35, -22),  # cut into the app
    (23.60, f"{LIB}/trimmed_click.mp3",  0.00, 0.25, -22),  # filter ticks
    (25.40, f"{LIB}/sfx_tick.mp3",       0.00, 0.40, -28),  # light bed under typing
    (27.10, f"{LIB}/trimmed_cash.mp3",   0.00, 1.60, -22),  # the payoff lands
]


def sfx_gain(path, start, length, target_db):
    """dB of gain needed to bring this slice to target_db mean."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", str(start), "-t", str(length),
         "-i", path, "-af", "volumedetect", "-f", "null", "/dev/null"],
        capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+)", out)
    return target_db - float(m.group(1)) if m else 0.0


def load_words():
    r = json.load(open(VO))
    out = []
    for s in r["segments"]:
        for w in s["words"]:
            t = FIXES.get(w["word"].strip(), w["word"].strip())
            out.append({"word": t, "start": w["start"], "end": w["end"]})
    return out


def wrap(draw, text, font, max_w):
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


def punch(img, t):
    for s, e, z in PUNCHES:
        if s <= t < e:
            cw, ch = int(W / z), int(H / z)
            x, y = (W - cw) // 2, (H - ch) // 2
            return img.crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS)
    return img


def draw_block(d, lines, font, y0, lh, fill, stroke):
    for j, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        d.text((W // 2 - tw / 2, y0 + j * lh), ln, font=font,
               fill=fill, stroke_width=stroke, stroke_fill=BLACK)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    words = load_words()
    f_el = ImageFont.truetype(FONT, EL_SIZE)
    f_en = ImageFont.truetype(FONT, EN_SIZE)
    f_hook = ImageFont.truetype(F_TITLE, HOOK_SIZE)

    bub_imgs = {}
    for path, *_ in BUBBLES:
        im = Image.open(path).convert("RGBA")
        r = min(BUB_MAX_W / im.width, 1.0)
        bub_imgs[path] = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)

    ov_imgs = {}
    for path, *_, mx in OVERLAYS:
        im = Image.open(path).convert("RGBA")
        r = min(mx / im.width, mx / im.height, 1.0)
        ov_imgs[path] = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    caps = []
    for s, e, el, en in BILINGUAL:
        hook = s < HOOK_STYLE_END
        fnt = f_hook if hook else f_el
        caps.append({"start": s, "end": e, "hook": hook,
                     "el": wrap(d0, el, fnt, MAX_W),
                     "en": wrap(d0, en, f_en, MAX_W)})

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", SRC],
        capture_output=True, text=True).stdout.strip())
    n = int(dur * FPS)

    dec = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", SRC, "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
         "-crf", "18", "-pix_fmt", "yuv420p", TMP], stdin=subprocess.PIPE)

    fsize = W * H * 3
    el_lh, en_lh = EL_SIZE + LINE_SP, EN_SIZE + 8
    for i in range(n):
        raw = dec.stdout.read(fsize)
        if len(raw) < fsize:
            break
        t = i / FPS
        img = punch(Image.frombytes("RGB", (W, H), raw), t)

        for path, os_, oe, ox, oy, _ in OVERLAYS:
            if os_ <= t < oe:
                im = ov_imgs[path]
                p = (t - os_) / max(oe - os_, 1e-6)
                if p < 0.12:                       # pop in
                    sc = 0.70 + 0.30 * (p / 0.12) ** 0.5
                elif p > 0.90:                     # ease out
                    sc = 1.0 - 0.22 * ((p - 0.90) / 0.10)
                else:
                    sc = 1.0
                sw, sh = max(1, int(im.width * sc)), max(1, int(im.height * sc))
                sm = im.resize((sw, sh), Image.LANCZOS)
                img.paste(sm, (int(ox * W - sw / 2), int(oy * H - sh / 2)), sm)

        for path, ap, bx, by in BUBBLES:
            if ap <= t < BUB_END:
                im = bub_imgs[path]
                p = min((t - ap) / 0.18, 1.0)
                sc = 0.72 + 0.28 * (p ** 0.5)               # quick pop-in, then hold
                sw, sh = max(1, int(im.width * sc)), max(1, int(im.height * sc))
                sm = im.resize((sw, sh), Image.LANCZOS)
                img.paste(sm, (int(bx * W - sw / 2), int(by * H - sh / 2)), sm)

        d = ImageDraw.Draw(img)


        cap = next((c for c in caps if c["start"] <= t < c["end"]), None)
        if cap:
            fnt = f_hook if cap["hook"] else f_el
            lh = (HOOK_SIZE + LINE_SP) if cap["hook"] else el_lh
            stroke = HOOK_STROKE if cap["hook"] else EL_STROKE
            el_h = len(cap["el"]) * lh
            en_h = (GAP + len(cap["en"]) * en_lh) if cap["en"] else 0
            y0 = int(H * SUB_Y) - (el_h + en_h) // 2
            draw_block(d, cap["el"], fnt, y0, lh, WHITE, stroke)
            if cap["en"]:
                draw_block(d, cap["en"], f_en, y0 + el_h + GAP, en_lh, EN_GREY, EN_STROKE)

        enc.stdin.write(img.tobytes())

    enc.stdin.close(); dec.stdout.close()
    enc.wait(); dec.wait()

    # mix SFX under the original audio
    inputs, filt, mix = ["-i", TMP, "-i", SRC], [], ["[1:a]"]
    for k, (at, path, cs, ln, tgt) in enumerate(SFX):
        if not os.path.exists(path):
            print("MISSING SFX:", path); continue
        g = sfx_gain(path, cs, ln, tgt)
        print(f"  sfx {os.path.basename(path):38} gain {g:+5.1f} dB")
        inputs += ["-ss", str(cs), "-t", str(ln), "-i", path]
        filt.append(f"[{k+2}:a]afade=t=out:st={max(ln-0.12,0):.2f}:d=0.12,"
                    f"asetpts=PTS-STARTPTS,volume={g:.1f}dB,"
                    f"adelay={int(at*1000)}|{int(at*1000)}[s{k}]")
        mix.append(f"[s{k}]")
    filt.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.97[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", OUT], check=True)
    os.remove(TMP)
    print("DONE ->", OUT)


if __name__ == "__main__":
    main()
