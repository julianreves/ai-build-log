"""Thumbnail = a frame of the finished base video + the spec's headline at full strength (no headline in the spec: the bare frame).
16:9 -> 1920x1080 with the headline in a side column; 4:5 (CLIP_FMT=tall) -> 1080x1350 with the headline low on the frame, under the face.
usage: thumb.py <time_in_final_video_seconds> <out.png> [L|R]     (side = which side the headline text goes on; 16:9 only)
Pick a time when the speaker's face is clear and not covered by the text (check with `clip preview`)."""
import sys, subprocess, os
from PIL import Image
t_sel, out = float(sys.argv[1]), os.path.abspath(sys.argv[2]); side = sys.argv[3] if len(sys.argv) > 3 else None
sys.argv = ["x", "ovthumb"]
import events as EVM
from plan import *
os.chdir(out_dir())
import overlays as O
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t_sel:.4f}", "-i", "base_video.mp4", "-frames:v", "1", "_thumb_base.png"], check=True)
base = Image.open("_thumb_base.png").convert("RGBA")
cv = Image.new("RGBA", (O.W, O.H), (0, 0, 0, 0))
if EVM.HEAD:
    EVM.HEAD = dict(EVM.HEAD)
    if O.TALL: EVM.HEAD["side"] = "L"
    elif side: EVM.HEAD["side"] = side
    O.build_head_sprites(EVM.HEAD)
    if O.TALL:
        # headline sits in the lower part of the frame over a bottom-up scrim (the face is centred in a 4:5 crop, so no side column)
        y = 0.0
        for i, (sp, sz, f) in enumerate(O.S["hl"]): y += sz * (1.38 if i == len(O.S["hl"]) - 1 else f)
        EVM.HEAD["y0"] = O.H - 150 - (y + 80)
        grad = Image.new("L", (1, O.H)); top = EVM.HEAD["y0"] - 260
        grad.putdata([0 if yy < top else int(215 * min(1.0, (yy - top) / 320.0)) for yy in range(O.H)])
        scrim = Image.new("RGBA", (O.W, O.H), O.NEAR_BLACK + (255,)); scrim.putalpha(grad.resize((O.W, O.H)))
        cv = Image.alpha_composite(cv, scrim)
        O.S["scrimL"] = O.S["scrimR"] = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    O.draw_headline(cv, dict(t_in=-5.0, t_out=999.0), 0.0, 1.0, 1.0)
os.makedirs(os.path.dirname(out), exist_ok=True)
Image.alpha_composite(base, cv).convert("RGB").save(out)
os.remove("_thumb_base.png")
print(out)
