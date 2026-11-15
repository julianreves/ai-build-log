"""Make the readable, timestamped transcript the agent uses to choose clips.   (run with venv39 -I for the whisper fallback)
usage: transcript.py [--whisper]
Default: YouTube captions (word-level times, free, instant).  --whisper (or no captions available): local faster-whisper
medium.en over the whole audio (slow: roughly real-time on this Mac).  Output: source/transcript.md (+ words json)."""
import json, os, subprocess, sys
from common import *
sys.path.insert(0, LIB)
import ytcaps
force = "--whisper" in sys.argv
job = load_job(); cap = job.get("captions")
os.makedirs(f"{JOB}/source", exist_ok=True)
if cap and os.path.exists(f"{JOB}/{cap}") and not force:
    words = ytcaps.parse(f"{JOB}/{cap}"); how = "YouTube captions"
else:
    from faster_whisper import WhisperModel
    print("transcribing the whole audio with whisper (slow)...", flush=True)
    wav = f"{JOB}/work/audio16.wav"; os.makedirs(f"{JOB}/work", exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", SRC, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    m = WhisperModel("medium.en", device="cpu", compute_type="int8", cpu_threads=8)
    segs, _ = m.transcribe(wav, word_timestamps=True, language="en", vad_filter=True, beam_size=5, initial_prompt=glossary_prompt() or None)
    words = [dict(w=w.word.strip(), s=round(w.start, 3), e=round(w.end, 3)) for s in segs for w in s.words]
    json.dump(words, open(f"{JOB}/source/words_whisper.json", "w")); how = "local whisper medium.en"
    os.remove(wav)
md = ytcaps.markdown(words)
head = f"# Transcript — {job.get('title','')}\nSource: {job.get('url','')}  |  channel: {job.get('channel','')}  |  duration {ts(job.get('duration',0),0)}  |  transcript from {how}\n" \
       "Times are SOURCE seconds shown as [mm:ss]. '»' marks a speaker change in YouTube captions. Wording of auto-captions is approximate: names and terms are often wrong — verify against audio before quoting.\n\n"
open(f"{JOB}/source/transcript.md", "w").write(head + md + "\n")
job["transcript"] = "source/transcript.md"; job["transcript_from"] = how; save_job(job)
print(f"{len(words)} words -> {JOB}/source/transcript.md  ({how})")
