"""Cut the segments from the source, apply optional punch-in crops, cross-dissolve the joins.
Outputs (in the clip work dir): base_video.mp4 (no audio, CRF 10), base_audio_raw.wav, filter_base.txt

Spec fields used:
  segments[i]: a, b (source seconds), x (join length in frames), vend (hold last frame after this source second)
  crops: {"name": [w, h, x, y]}   rectangles in the 1920x1080-scaled frame, scaled back up to full frame
  crop_windows: [[src_a, src_b, "name"], ...]   source-time windows where a crop replaces the full frame
  tall: {"x": 0.5, "windows": [[src_a, src_b, x], ...]}   4:5 version only (CLIP_FMT=tall): horizontal centre of the 1080x1350 crop,
        as a fraction of the 16:9 frame width (0 = far left, 1 = far right); windows override it for a source-time range (per shot)."""
import json, subprocess, os, sys
from plan import *
OUT = out_dir(); os.chdir(OUT)
CROPS = C.get("crops", {})
WINDOWS = C.get("crop_windows", [])
def seg_modes(sg):
    """[(t0,t1,name)] relative to the segment start, from the absolute crop windows"""
    res = []
    for a, b, name in WINDOWS:
        lo = max(a, sg["src_in"]); hi = min(b, sg["src_out"])
        if hi - lo > 1e-6: res.append([lo - sg["src_in"], hi - sg["src_in"], name])
    return res
TALL = C.get("tall") or {}
def tall_px(x):
    """crop centre (fraction of the frame width) -> left edge of the 1080-px window in the 2400-px-wide scaled frame"""
    return int(round(max(0, min(TALL_SRC_W - OUT_W, float(x) * TALL_SRC_W - OUT_W / 2))))
def tall_filter(i, sg):
    """[w{i}] (the finished 16:9 segment) -> [v{i}] cropped to 4:5, following the speaker per shot"""
    x0 = tall_px(TALL.get("x", 0.5)); expr = str(x0)
    for a, b, x in TALL.get("windows", []):
        lo = max(a, sg["src_in"]) - sg["src_in"]; hi = min(b, sg["src_out"]) - sg["src_in"]
        if hi - lo > 1e-6: expr += f"+({tall_px(x) - x0})*gte(t,{lo-0.02:.4f})*lt(t,{hi-0.02:.4f})"
    return f"[w{i}]scale={TALL_SRC_W}:{OUT_H}:flags=lanczos,crop=w={OUT_W}:h={OUT_H}:x='{expr}':y=0,setsar=1[v{i}]"
def run_build():
    inputs = []; vf = []; af = []; lab = "w" if FMT == "tall" else "v"
    for i, s in enumerate(segs):
        pre = min(1.0, s["src_in"])                   # pre-roll before the in point
        S = s["src_in"] - pre
        inputs += ["-ss", f"{S:.6f}", "-t", f"{s['n']*FT+pre+1.0:.6f}", "-i", SRC]
        dur = s["n"] * FT
        modes = seg_modes(s)
        vend = s.get("vend"); vhold = ""
        trim_end = pre + dur - 0.02
        if vend:
            L = vend - s["src_in"]; trim_end = pre + L - 0.02
            vhold = f",tpad=stop_mode=clone:stop_duration={dur - L + 0.1:.6f}"
        base = (f"[{i}:v:0]trim=start={pre-0.01:.6f}:end={trim_end:.6f},setpts=PTS-STARTPTS,"
                f"scale=1920:1080:flags=lanczos,fps={FPS},format=yuv420p,setsar=1{vhold}")
        by = {}
        for a, b, m in modes: by.setdefault(m, []).append((a, b))
        if not by:
            vf.append(f"{base}[{lab}{i}]")
        else:
            ms = list(by)
            vf.append(f"{base},split={len(ms)+1}[m{i}]" + "".join(f"[c{i}{m}]" for m in ms))
            cur = f"m{i}"
            for j, m in enumerate(ms):
                w, h, x, y = CROPS[m]
                vf.append(f"[c{i}{m}]crop={w}:{h}:{x}:{y},scale=1920:1080:flags=lanczos,unsharp=5:5:0.45:5:5:0.0,setsar=1[z{i}{m}]")
                en = "+".join(f"gte(t,{a-0.02:.4f})*lt(t,{b-0.02:.4f})" for a, b in by[m])
                outn = f"{lab}{i}" if j == len(ms) - 1 else f"o{i}{j}"
                vf.append(f"[{cur}][z{i}{m}]overlay=0:0:enable='{en}'[{outn}]")
                cur = outn
        if FMT == "tall": vf.append(tall_filter(i, s))
        af.append(f"[{i}:a:0]atrim=start={pre:.6f}:duration={dur:.6f},asetpts=PTS-STARTPTS,aresample=48000,"
                  f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
    cur = "v0"; cum = segs[0]["n"]
    for i in range(1, len(segs)):
        x = segs[i]["x"]; off = (cum - x) * FT
        vf.append(f"[{cur}][v{i}]xfade=transition=fade:duration={x*FT:.6f}:offset={off:.6f}[vx{i}]")
        cur = f"vx{i}"; cum += segs[i]["n"] - x
    vf.append(f"color=c=0x111318:s={OUT_W}x{OUT_H}:r={FPS}:d={CARD*FT:.6f},format=yuv420p,setsar=1[card]")
    vf.append(f"[{cur}][card]concat=n=2:v=1:a=0[vout]")
    acur = "a0"
    for i in range(1, len(segs)):
        af.append(f"[{acur}][a{i}]acrossfade=d={segs[i]['x']*FT:.6f}:c1=qsin:c2=qsin[ax{i}]")
        acur = f"ax{i}"
    af.append(f"[{acur}]afade=t=out:st={(INTERVIEW_FRAMES*FT)-0.05:.6f}:d=0.05[aend]")
    af.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={CARD*FT:.6f},asetpts=PTS-STARTPTS[sil]")
    af.append("[aend][sil]concat=n=2:v=0:a=1[aout]")
    open("filter_base.txt", "w").write(";".join(vf + af))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats"] + inputs + ["-/filter_complex", "filter_base.txt",
        "-map", "[vout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", "-r", FPS, "-an", "base_video.mp4",
        "-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", "base_audio_raw.wav"]
    subprocess.run(cmd, check=True)
if __name__ == "__main__": run_build()
