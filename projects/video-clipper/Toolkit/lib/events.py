"""Editorial graphics, driven entirely by the clip spec (see Toolkit/SPEC_REFERENCE.md).
Verbatim quote cards must only contain words that are spoken in the clip (check.py enforces this);
editorial lines (kickers, closing card) carry no quotation marks.
Anchors ("when does it appear?") are resolved against tokens.json, written by captions.py."""
import json, re
from common import clip_spec, clip_spec_en, norm, LANG, is_clean
C = clip_spec()
CLEAN = is_clean(C)
HEAD = C.get("headline")                      # clean look: only used for the thumbnail
PILLS = C.get("pills", {})
CARDS = C.get("cards", {})
HEROES = C.get("heroes", {})
STATS = C.get("stats", {})
CARD = C.get("closing", {})                   # clean look: only "src" is shown (the short source card)
HL = C.get("highlights", [])
SCHED = C.get("schedule", [])
_TOK = None
def toks():
    global _TOK
    if _TOK is None: _TOK = json.load(open("tokens.json"))
    return _TOK
def find(phrase, nth=0):
    P = [norm(w) for w in phrase.split()]; T = toks(); n = 0
    for i in range(len(T) - len(P) + 1):
        if all(T[i + k]["n"] == P[k] for k in range(len(P))):
            if n == nth: return i, i + len(P) - 1
            n += 1
    raise KeyError(f"anchor phrase not found in the clip's spoken words: {phrase!r} (nth={nth})")
def at(spec):
    """spec: seconds (number) | [phrase, 's'|'e', offset_seconds, nth]"""
    if isinstance(spec, (int, float)): return float(spec)
    phrase, which = spec[0], spec[1]; off = spec[2] if len(spec) > 2 else 0; nth = spec[3] if len(spec) > 3 else 0
    i, j = find(phrase, nth); T = toks()
    return (T[i]["s"] if which == "s" else T[j]["e"]) + off
def schedule(T=None):
    out = []
    for e in SCHED:
        if CLEAN and e.get("k") != "pill": continue          # clean look: pills only (speaker name, fairness labels)
        e = dict(e); anchor = e["t_in"]
        for k in ("t_in", "t_out"): e[k] = at(e[k])
        if "hero_t" in e: e["hero_t"] = [at(x) for x in e["hero_t"]]
        if e["k"] == "card" and not isinstance(anchor, (int, float)):
            # word-synchronous reveal: match the card's words to the spoken tokens that follow the anchor
            Tk = toks(); j = find(anchor[0], anchor[3] if len(anchor) > 3 else 0)[0]; wt = []
            split_w = lambda txt: [norm(w) for w in re.split(r"[\s|*]+", txt) if norm(w)]
            words = split_w(clip_spec_en()["cards"][e["key"]]["text"] if LANG == "es" else CARDS[e["key"]]["text"])   # always the spoken (English) words
            for w in words:
                k2 = j
                while k2 < min(len(Tk), j + 4) and Tk[k2]["n"] != w: k2 += 1
                if k2 < min(len(Tk), j + 4): wt.append(Tk[k2]["s"]); j = k2 + 1
                else: wt.append(wt[-1] if wt else e["t_in"])
            if LANG == "es":      # spread the Spanish words over the English word times (same reveal pace, different word count)
                n_es = len(split_w(CARDS[e["key"]]["text"])); wt = [wt[min(len(wt) - 1, int(i * len(wt) / max(1, n_es)))] for i in range(n_es)]
            e["words_t"] = wt
        out.append(e)
    return out
