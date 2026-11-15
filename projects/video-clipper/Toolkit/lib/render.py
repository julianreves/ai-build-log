"""Overlay frames -> final MP4.   usage: render.py <out.mp4> [--keep-frames]
Measures loudness of base_audio_raw.wav, renders the Pillow overlay PNG sequence (overlays.py), then composites with
ffmpeg: x264 slow CRF 18 High, bt709-tagged, AAC 192k, highpass 70 Hz + two-pass linear loudnorm to -16 LUFS, TP -1.5."""
import os, re, shutil, subprocess, sys
from plan import *
out = os.path.abspath(sys.argv[1]); keep = "--keep-frames" in sys.argv
os.chdir(out_dir())
r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", "base_audio_raw.wav", "-af",
                    "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
g = lambda k: re.search(r'"%s"\s*:\s*"([-\d.]+)"' % k, r.stderr).group(1)
I, TP, LRA, TH, OFF = (g("input_i"), g("input_tp"), g("input_lra"), g("input_thresh"), g("target_offset"))
print(f"loudness measured: I={I} TP={TP} LRA={LRA}", flush=True)
shutil.rmtree("ov", ignore_errors=True)
run([PY, f"{LIB}/overlays.py", "ov"], stdout=open("ov.log", "w"), stderr=subprocess.STDOUT)
fc = ("[1:v]scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[ov];"
      "[0:v][ov]overlay=0:0:format=yuv420:shortest=1,format=yuv420p[v];"
      f"[2:a]highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={I}:measured_TP={TP}:measured_LRA={LRA}:measured_thresh={TH}:offset={OFF}:linear=true,"
      "alimiter=limit=0.89:level=false,aresample=48000[a]")
os.makedirs(os.path.dirname(out), exist_ok=True)
run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", "base_video.mp4", "-framerate", FPS, "-i", "ov/f%05d.png",
     "-i", "base_audio_raw.wav", "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
     "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", FPS,
     "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
if not keep: shutil.rmtree("ov", ignore_errors=True)
print("rendered", out)
