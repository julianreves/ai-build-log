"""YouTube caption (.vtt) parsing -> word stream with times.  Auto-captions carry inline word timestamps
(<00:00:01.000><c> word</c>); every word appears exactly once on a 'tagged' line, which is what we collect.
Manual captions (no inline tags) fall back to cue-level timing.   '>>' speaker-change markers are kept as '>>'."""
import re, json, os, sys
_T = re.compile(r"(\d+):(\d+):([\d.]+)")
def _sec(m): return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
def clean(w): return w.replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
def parse(path):
    txt = open(path, encoding="utf8").read(); cues = re.split(r"\n\n+", txt); words = []; tagged = "<c>" in txt
    last_plain = ""
    for c in cues:
        m = re.match(r"(\d+:\d+:[\d.]+) --> (\d+:\d+:[\d.]+)", c)
        if not m: continue
        s = _sec(_T.match(m[1])); e = _sec(_T.match(m[2]))
        for ln in c.split("\n")[1:]:
            if tagged:
                if "<c>" not in ln: continue
                # leading untagged word(s) start at the cue start
                parts = re.split(r"<(\d+:\d+:[\d.]+)>", ln)           # [lead, t1, chunk1, t2, chunk2 ...]
                lead = re.sub(r"</?c>", "", parts[0]).strip()
                for w in lead.split(): words.append([clean(w), s])
                for i in range(1, len(parts) - 1, 2):
                    t = _sec(_T.match(parts[i])); chunk = re.sub(r"</?c>", "", parts[i + 1]).strip()
                    for w in chunk.split(): words.append([clean(w), t])
            else:
                t = re.sub(r"<[^>]+>", "", ln).strip()
                if t and t != last_plain:
                    ws = t.split()
                    for k, w in enumerate(ws): words.append([clean(w), s + (e - s) * k / max(1, len(ws))])
                    last_plain = t
    out = []
    for w, t in words:
        if re.fullmatch(r"\[[^\]]*\]|\(.*\)", w): continue            # [music] etc.
        out.append(dict(w=w, s=round(t, 3)))
    for i, x in enumerate(out): x["e"] = out[i + 1]["s"] if i + 1 < len(out) else x["s"] + 0.3
    return out
def plain_stream(words):
    """normalised word list for verbatim checks"""
    n = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    return [n(x["w"]) for x in words if n(x["w"])]
def markdown(words, every=18):
    """readable transcript: '[mm:ss] text' lines of ~every words, '>>' starts a new line"""
    lines = []; cur = []; t0 = 0
    for x in words:
        if x["w"] == ">>" or x["w"].startswith(">>"):
            if cur: lines.append((t0, " ".join(cur))); cur = []
            t0 = x["s"]; cur = ["»" + x["w"].lstrip(">")] if x["w"].lstrip(">") else ["»"]
            continue
        if not cur: t0 = x["s"]
        cur.append(x["w"])
        if len(cur) >= every and x["w"][-1:] in ".?!": lines.append((t0, " ".join(cur))); cur = []
        elif len(cur) >= every + 14: lines.append((t0, " ".join(cur))); cur = []
    if cur: lines.append((t0, " ".join(cur)))
    return "\n".join(f"[{int(t//3600)}:{int(t%3600//60):02d}:{int(t%60):02d}] {s}" if t >= 3600 else f"[{int(t//60):02d}:{int(t%60):02d}] {s}" for t, s in lines)
if __name__ == "__main__":
    w = parse(sys.argv[1]); print(len(w), "words"); print(markdown(w)[:1500])
