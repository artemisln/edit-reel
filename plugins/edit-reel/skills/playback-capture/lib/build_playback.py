#!/usr/bin/env python3
"""Build one continuous playback video to play fullscreen and film with a phone in one take.

Every beat should be held ~50% longer than its expected voiceover line, so if a line runs long
there is still screen left. Black at head and tail gives a clean start/stop and an easy sync
marker in the phone footage. They are added automatically if the beat list does not start and
end with one.

    python3 build_playback.py beats.json

beats.json (see beats_example.json):
{
  "output": "playback.mp4",
  "width": null,           native screen-recording width; null = take it from the first source
  "height": null,          native screen-recording height; null = take it from the first source
  "fps": 30,
  "black": 1.5,            seconds of black at head and tail
  "beats": [
    {"label": "B1 hook", "src": "rec1.mov", "in": 20.5, "duration": 5.0, "line": "VO line"},
    {"label": "B2 gap",  "src": null, "duration": 2.0, "line": "black filler"}
  ]
}

Relative "src" paths resolve against the folder that holds beats.json.
Writes the video plus beatmap.json (exact in/out of every beat) next to it.
"""
import json, os, subprocess, sys


def probe_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = (int(x) for x in out.split(",")[:2])
    return w, h


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg_path = os.path.abspath(sys.argv[1])
    base = os.path.dirname(cfg_path)
    cfg = json.load(open(cfg_path))

    beats = []
    for b in cfg["beats"]:
        b = dict(b)
        if b.get("src"):
            b["src"] = b["src"] if os.path.isabs(b["src"]) else os.path.join(base, b["src"])
            if not os.path.exists(b["src"]):
                sys.exit(f"missing source: {b['src']}")
        beats.append(b)
    if not beats:
        sys.exit("no beats in config")

    black = float(cfg.get("black", 1.5))
    if not beats[0]["label"].startswith("black"):
        beats.insert(0, {"label": "black-lead", "src": None, "duration": black,
                         "line": "settle before the first line"})
    if not beats[-1]["label"].startswith("black"):
        beats.append({"label": "black-tail", "src": None, "duration": black,
                      "line": "clean stop"})

    W, H = cfg.get("width"), cfg.get("height")
    if not (W and H):
        first = next((b["src"] for b in beats if b.get("src")), None)
        if not first:
            sys.exit("set width/height in the config when no beat has a source")
        W, H = probe_size(first)
    fps = int(cfg.get("fps", 30))
    out = cfg.get("output", "playback.mp4")
    out = out if os.path.isabs(out) else os.path.join(base, out)
    work = os.path.dirname(out)

    # cover-fit to the native size so it plays back 1:1 fullscreen
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1"
    common = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
              "-an", "-bf", "0", "-force_key_frames", "expr:eq(n,0)"]

    print(f"output {W}x{H} @ {fps}fps -> {out}")
    parts, cursor, beatmap = [], 0.0, []
    for i, b in enumerate(beats):
        p = os.path.join(work, f"_p{i:02d}.mp4")
        d = float(b["duration"])
        if not b.get("src"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"color=c=black:s={W}x{H}:r={fps}:d={d}", *common, p],
                           check=True)
        else:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(b["in"]),
                            "-t", str(d), "-i", b["src"], "-vf", vf, *common, p], check=True)
        got = duration(p)
        beatmap.append({"beat": b["label"], "starts_at": round(cursor, 2),
                        "ends_at": round(cursor + got, 2), "duration": round(got, 2),
                        "line": b.get("line", "")})
        print(f"  {cursor:6.2f}s  {b['label']:14} {got:5.2f}s   {b.get('line', '')}")
        cursor += got
        parts.append(p)

    lst = os.path.join(work, "_concat.txt")
    with open(lst, "w") as f:
        f.write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
    for p in parts:
        os.remove(p)
    os.remove(lst)
    bm = os.path.join(work, "beatmap.json")
    with open(bm, "w") as f:
        json.dump(beatmap, f, indent=1)
    print(f"\nDONE -> {out}  total {cursor:.2f}s\nbeatmap -> {bm}")


if __name__ == "__main__":
    main()
