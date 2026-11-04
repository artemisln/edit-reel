#!/usr/bin/env python3
"""Find where the playback video sits inside the filmed take, using its black head and tail.

Measures only the screen band so the lit room does not skew the average. Prints the offset and
the mapped in/out of every beat.

    python3 find_offset.py <filmed.mov> <beatmap.json> [screen_crop]

screen_crop defaults to the full frame; pass an ffmpeg crop like "crop=2160:1300:0:1100" to
restrict the measurement to the laptop screen.
"""
import subprocess, sys, json, os, tempfile
import numpy as np
from PIL import Image

filmed = sys.argv[1]
beatmap = json.load(open(sys.argv[2]))
crop = sys.argv[3] if len(sys.argv) > 3 else None

dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                            "-of","csv=p=0",filmed],capture_output=True,text=True).stdout)
vf = (crop + ",") if crop else ""
vals = []
frame = os.path.join(tempfile.mkdtemp(prefix="find_offset_"), "frame.png")
for i in range(int(dur*10)):
    t = i/10
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",f"{t:.2f}","-i",filmed,
                    "-frames:v","1","-vf",f"{vf}scale=160:-1","-q:v","5",frame],check=True)
    vals.append((t, np.array(Image.open(frame).convert("L"),dtype=np.float32).mean()))

arr = np.array([v for _, v in vals])
thr = np.percentile(arr, 20)
runs, cur = [], None
for t, m in vals:
    if m <= thr:
        cur = [t, t] if cur is None else [cur[0], t]
    elif cur:
        runs.append(tuple(cur)); cur = None
if cur: runs.append(tuple(cur))
runs = [r for r in runs if r[1]-r[0] >= 0.4]
if len(runs) < 2:
    sys.exit(f"expected a dark head and tail, found {len(runs)}: {runs}")

lead, tail = runs[0], runs[-1]
pb_lead_end = next(b["ends_at"] for b in beatmap if b["beat"].startswith("black"))
pb_tail_start = [b["starts_at"] for b in beatmap if b["beat"].startswith("black")][-1]
offset = lead[1] - pb_lead_end

pb_len = pb_tail_start - pb_lead_end
fl_len = tail[0] - lead[1]
print(f"playback content : {pb_len:.2f}s")
print(f"filmed   content : {fl_len:.2f}s   drift {fl_len-pb_len:+.2f}s")
print(f"OFFSET           : {offset:.2f}s\n")
# the scan steps in 0.1s, so anything under ~0.15s is measurement noise, not real drift
if abs(fl_len - pb_len) > 0.15:
    print("WARNING: real drift detected. Derive the offset per beat instead of one constant.\n")
else:
    print("drift is within the 0.1s sampling resolution, a single offset is safe.\n")

print(f"{'beat':14}{'playback':>16}{'in the filmed take':>24}")
for b in beatmap:
    if b["beat"].startswith("black"): continue
    print(f"{b['beat']:14}{b['starts_at']:7.2f}-{b['ends_at']:6.2f}"
          f"{b['starts_at']+offset:11.2f}-{b['ends_at']+offset:6.2f}")
