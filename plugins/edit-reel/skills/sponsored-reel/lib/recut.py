"""Picture-only recut: swap in reshot clips, digitally zoom a shot, lift a dark opener.

The audio is untouched, only the picture changes, so every voiceover timing stays valid.

Usage:
    python3 recut.py <project-dir>

Edit SEGS below for your video. Every path is relative to the project directory.
"""
import os
import subprocess
import sys

PROJECT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

V1 = f"{PROJECT}/edited/v1_cuts_no_subs.mp4"    # the current cut, carries the master audio
NEW = f"{PROJECT}/raw/new_clips"                # reshot clips
OUT = f"{PROJECT}/work/recut_v2.mp4"

W, H, FPS = 1080, 1920, 30

# (source, in, out, filter) laid end to end. Durations must total the length of V1.
# Example layout for a ~29s reel; replace with your own segments.
SEGS = [
    # the desk hook, shadows lifted because the room read too dark
    (V1, 0.00, 2.93, "eq=brightness=0.06:contrast=1.04:saturation=1.05"),
    # reshoots: steadier, and close enough that the typed URL actually reads
    (f"{NEW}/clip_url_1.mov", 4.00, 6.14, None),
    (V1, 5.07, 7.07, None),
    (f"{NEW}/clip_url_2.mov", 2.50, 4.76, None),
    # the pasted prompt, pushed in 1.45x so the text reads (fine from a 4K source)
    (V1, 9.33, 12.43, "crop=iw/1.45:ih/1.45:(iw-iw/1.45)*0.42:(ih-ih/1.45)*0.46"),
    (V1, 12.43, 26.94, None),
    # the closing shot, picked by scoring every 2.5s window on motion and colour
    (f"{NEW}/clip_outro.mov", 65.20, 67.66, None),
]


def probe_duration(path):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    parts = []
    for i, (src, a, b, filt) in enumerate(SEGS):
        p = f"{PROJECT}/work/_seg{i}.mp4"
        vf = f"{filt}," if filt else ""
        vf += f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a), "-to", str(b),
                        "-i", src, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                        "-crf", "17", "-pix_fmt", "yuv420p", p], check=True)
        d = probe_duration(p)
        print(f"  seg{i}  {os.path.basename(src):26} {a:6.2f}-{b:6.2f}  -> {d:5.2f}s")
        parts.append(p)

    lst = f"{PROJECT}/work/_concat.txt"
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")

    # concat picture, then re-attach the original audio untouched
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-i", V1, "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", OUT], check=True)

    for p in parts:
        os.remove(p)
    os.remove(lst)
    print(f"DONE -> {OUT}  ({probe_duration(OUT):.2f}s, source {probe_duration(V1):.2f}s)")


if __name__ == "__main__":
    main()
