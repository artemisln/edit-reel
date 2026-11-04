#!/usr/bin/env python3
"""
trim-raw-video / render.py
Render a finished cut from a cut-list JSON. Splices the chosen segments,
loudness-matches them, optionally re-frames the aspect ratio, adds gentle
in/out fades, and concatenates -- one clean video out.

Usage:  python3 render.py cutlist.json

cutlist.json schema:
{
  "output":   "final.mp4",
  "aspect":   "keep",          keep | 9:16 | 16:9 | 1:1 | 4:5 | 3:4
  "crop_x":   "center",        crop X offset in DISPLAY pixels, or "center"
  "crop_y":   "center",        crop Y offset in DISPLAY pixels, or "center"
  "scale":    null,            "1080x1920" forces output size; null = no rescale
  "fps":      null,            e.g. 30; null = keep source fps
  "fade_in":  0.12,
  "fade_out": 0.25,
  "loudness": -16,             per-segment loudnorm LUFS target; null disables
  "crf":      18,
  "preset":   "fast",
  "segments": [ {"src": "part_1.MOV", "start": 0.80, "end": 4.05}, ... ]
}

Notes
- start/end are in DISPLAY time (seconds) of each source.
- Segments may come from different source files; loudnorm matches their levels.
- Rotated phone footage is handled automatically -- crop math uses DISPLAY size.
- Frame-accurate input-seek: only decodes from the keyframe before each cut.
"""
import sys, os, json, subprocess

WORK = "_trim_work"
ASPECT = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:5": 4 / 5, "3:4": 3 / 4}


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr + "\n")
        sys.exit(f"ffmpeg failed: {' '.join(cmd[:6])} ...")
    return p


def even(x):
    return int(round(x / 2)) * 2


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate",
                        "-show_entries", "stream_side_data=rotation",
                        "-of", "json", path], capture_output=True, text=True)
    st = json.loads(r.stdout)["streams"][0]
    W, H = int(st["width"]), int(st["height"])
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if sd.get("rotation") is not None:
            rot = int(sd["rotation"])
    swap = (abs(rot) % 180) == 90
    return ((H, W) if swap else (W, H))   # display W, H


def build_vf(cut, dW, dH):
    """Video filter chain + resulting output size."""
    chain, ow, oh = [], dW, dH
    aspect = cut.get("aspect", "keep")
    if aspect and aspect != "keep":
        if aspect not in ASPECT:
            sys.exit(f"unknown aspect: {aspect}")
        ar = ASPECT[aspect]
        cw = even(min(dW, dH * ar))         # biggest ar-box fitting the display frame
        ch = even(min(dH, dW / ar))
        if cw >= dW and ch >= dH:
            print(f"  (source is already {aspect} -- no crop needed)")
        cx, cy = cut.get("crop_x", "center"), cut.get("crop_y", "center")
        x = even((dW - cw) / 2) if cx in ("center", None) else int(cx)
        y = even((dH - ch) / 2) if cy in ("center", None) else int(cy)
        x = max(0, min(x, dW - cw))
        y = max(0, min(y, dH - ch))
        chain.append(f"crop={cw}:{ch}:{x}:{y}")
        ow, oh = cw, ch
    if cut.get("scale"):
        sw, shh = cut["scale"].lower().split("x")
        chain.append(f"scale={sw}:{shh}")
        ow, oh = int(sw), int(shh)
    if cut.get("fps"):
        chain.append(f"fps={cut['fps']}")
    chain.append("format=yuv420p")
    return ",".join(chain), (ow, oh)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cut = json.load(open(sys.argv[1]))
    segs = cut.get("segments") or []
    if not segs:
        sys.exit("cutlist has no segments")
    os.makedirs(WORK, exist_ok=True)

    dW, dH = probe(segs[0]["src"])
    vf, (ow, oh) = build_vf(cut, dW, dH)
    loud = cut.get("loudness", -16)
    crf = str(cut.get("crf", 18))
    preset = cut.get("preset", "fast")
    fade_in = float(cut.get("fade_in", 0.12))
    fade_out = float(cut.get("fade_out", 0.25))
    print(f"source display {dW}x{dH}  ->  output {ow}x{oh}  (aspect: {cut.get('aspect', 'keep')})")

    parts, n = [], len(segs)
    for i, s in enumerate(segs):
        start = float(s["start"])
        dur = round(float(s["end"]) - start, 3)
        v = vf
        a = [f"loudnorm=I={loud}:TP=-1.5:LRA=11"] if loud is not None else []
        if i == 0 and fade_in > 0:
            v += f",fade=t=in:st=0:d={fade_in}"
            a.append(f"afade=t=in:st=0:d={min(fade_in, 0.1)}")
        if i == n - 1 and fade_out > 0:
            st = round(dur - fade_out, 3)
            v += f",fade=t=out:st={st}:d={fade_out}"
            a.append(f"afade=t=out:st={st}:d={fade_out}")
        af = ",".join(a) if a else "anull"
        out = os.path.join(WORK, f"_rseg{i}.mp4")
        print(f"  seg{i}: {os.path.basename(s['src'])}  {start}-{s['end']}  ({dur}s)")
        # Single frame-accurate input-seek. Do NOT add an output-seek (-ss after
        # -i): combined with loudnorm it discards the filter's primed output and
        # silences short segments.
        sh(["ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-i", s["src"], "-t", str(dur),
            "-vf", v, "-af", af,
            "-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out])
        parts.append(out)

    listf = os.path.join(WORK, "_concat.txt")
    with open(listf, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.basename(p)}'\n")
    output = cut.get("output", "final.mp4")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", listf, "-c", "copy", "-movflags", "+faststart", output])
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", output], capture_output=True, text=True)
    print(f"\nDONE -> {output}   ({float(r.stdout or 0):.2f}s, {ow}x{oh})")


if __name__ == "__main__":
    main()
