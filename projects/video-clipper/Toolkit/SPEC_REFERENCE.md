# CLIP SPEC — `Jobs/<job>/clips/NN.json`

One JSON file per clip. `clip new <Short_Title>` creates it from `templates/clip.template.json`; **`examples/example_spec.json` is a finished spec in the current format** (built and QA-passed in both 16:9 and 4:5). All times are **source seconds** unless noted.

**Every clip uses the clean look and is built twice** (`clip build NN`): `NN_Title.mp4` (16:9) and `NN_Title_4x5.mp4` (4:5). The clean look draws only captions, pills and a short source card. The old graphics (headline animation, quote cards, heroes, stats, closing-card slogan) still exist behind `"style": "full"`, 16:9 only, and are documented at the end as legacy; `examples/amodei_0N.json` are specs in that old style.

```jsonc
{
  "slug": "01_Everything_Gets_Commoditized",    // output folder + file names (clip new sets NN_ prefix)
  "title": "...", "speakers": "...",             // for Review.md
  "segments": [ {...hook...}, {...passage...} ], // the cuts, in order; 30-45 s in total
  "tall": { "x": 0.70, "windows": [ [src_a, src_b, 0.36] ] },   // 4:5 crop: where the speaker is (below)
  "phrases": [ "caption phrase", ... ],          // captions; empty = auto-build a draft (review it!)
  "highlights": [ "key phrase", ... ],           // words shown in teal in captions
  "pills": { "who": ["SPEAKER NAME", "Title, Company"] },
  "schedule": [ {"k": "pill", "key": "who", "t_in": 0.3, "t_out": 4.5, "side": "R"} ],
  "closing": { "src": "Guest × Host · Channel" },   // the 1.5 s source card at the end
  "end_seconds": 1.5,                            // optional: length of that card
  "headline": {...},                             // thumbnail text only (not shown in the video)
  "thumb": { "t": 18.6, "side": "L" },           // thumbnail frame (final-video seconds) + headline side (16:9)
  "crops": {...}, "crop_windows": [...],         // optional punch-ins, both formats (below)
  "es": { ... },                                 // optional Spanish version (below)
  "caveats": [ "..." ]                           // shown in Review.md: everything the reviewer must know
}
```

## segments
`{"name":"S1","a":800.80,"b":821.74,"x":5,"vend":877.34,"hook":true}`
- `a`,`b`: in/out (source seconds), chosen **inside pauses** (`clip snap`). Snapped to the frame grid; `b` is floored so the clip never runs past it.
- `x`: cross-dissolve length in frames for the join *into* this segment (default 5; 2–3 when the speaker barely pauses; ignored for the first segment). Audio crossfades the same length.
- `vend`: hold the last video frame after this source second (use to hide a cutaway to the interviewer while the speaker finishes a sentence). Audio is unaffected.
- `hook`: only on the FIRST segment: marks it as the cold open (below). Lets segment 2 start earlier in the source than segment 1 without a warning.

## Cold open (the hook first) — every clip
The video opens with the strongest 3–6 s of the passage, then plays the passage from its start. In the first week viewers left after 7–24 s, before the point; the point now comes first.
1. **Pick the hook line**: one complete, self-contained, striking sentence (or two short ones) by the same speaker, usually the line the passage lands on or its boldest claim. 3–6 s. It must keep its meaning without the context (CHANNEL_BRIEF.md "Cold-open hooks").
2. **Cut it like any other segment**: start in the pause right before its first word (so audio begins on the word, no lead-in; nothing is spoken before 0.15 s), end in the pause after its last word (`clip pauses` / `clip snap`; verify the speaker with `clip look`). It is segment 1 with `"hook": true`.
3. **Segment 2 is the passage from its natural start**, with `"x": 2` (short dissolve: reads as a hard cut). The hook may be taken from inside segment 2's own range, so the speaker says the same thing again later. That is normal and wanted.
4. **Captions**: `phrases` must list the hook's phrases FIRST (they are speech in the cut like any other), then the passage's phrases. The anchors `["phrase","s",offset,nth]` take `nth` = 0 for the hook, 1 for the repeat.
5. **On screen during the hook:** the first caption (the hook line itself) and the speaker pill (`t_in` 0.3, out about when the hook ends). Nothing else. When the line comes back in the passage, put its key words in `highlights`.
6. **End of the hook must be the end of the sentence.** `clip pauses` can miss a short pause in a noisy room (it once missed a 0.37 s pause and a test hook stopped mid-sentence). Build once with `phrases` empty and read `work/clips/NN/phrases_auto.json`: the first line must be the whole hook sentence. If not, move `b` to the pause after the last word.
7. **Check**: `clip lint` warns if the hook is outside 2–7 s or the join isn't short; `clip preview NN` and `--tall`, and read the first frames.
```jsonc
"segments": [
  {"name": "H",  "a": 271.00, "b": 276.98, "hook": true},       // cold open: "You have to just accept that everything that you're doing is getting commoditized constantly."
  {"name": "S1", "a": 253.88, "b": 280.28, "x": 2}                // the passage from its start (he says the line again near the end)
],
"schedule": [
  {"k": "pill", "key": "who", "t_in": 0.3, "t_out": 4.6, "side": "R"},
  {"k": "pill", "key": "pg",  "t_in": ["does that mean", "s", -0.05], "t_out": 17.4, "side": "L"}     // the host asks a question: ends at the shot change
]
```

## tall (the 4:5 crop) — every clip
The 4:5 video is a 1080×1350 window cut from the 16:9 frame at full height, so it shows 45% of the frame's width. The spec says where to centre it:
`"tall": {"x": 0.70, "windows": [[263.47, 265.43, 0.36], ...]}`
- `x`: default centre, as a fraction of the frame width (0 = left edge, 1 = right edge; clamped so the window stays inside the frame). Put it on the speaker's face in the shot used most.
- `windows`: `[src_a, src_b, x]` overrides the centre for a source-time range. One per shot whose speaker sits elsewhere: the host's close-up, a wide shot, a reaction cutaway. Use the exact shot-change times from `clip cuts <a> <b>`; a window that starts late shows a frame of the wrong crop.
- How to find x: `clip look <a> <b>` (tiles are 640 px wide): x = face centre in px ÷ 640.
- While someone else talks inside one shot (a two-shot), you may add a window to move the crop to them; it reads as a cut. If their line is two words, leave the crop where it is.
- `crops`/`crop_windows` punch-ins are applied first (both formats), and `tall` positions then refer to the punched-in frame. Rarely needed now.
- Always look at `clip preview NN --tall`: the speaker in frame in EVERY tile, head not cut off.

## pills (the only graphics in the clean look)
`"pills": {"who": ["SPEAKER NAME", "Title, Company"], "ctx": ["A HYPOTHETICAL", null]}` — `[label, sub-line or null]`, shown by a schedule event:
`{"k": "pill", "key": "who", "t_in": 0.3, "t_out": 4.5, "side": "L"}`
- In the clean look pills are **lower-thirds**: they sit just above the captions (y 690 in 16:9, 800 in 4:5), so they never cover a face. `side` L|R: put the name on the side of the frame where that person is in the 16:9 wide shot. `"y_clean"` overrides the height if a shot needs it. (`"y"` only applies to `"style": "full"`.)
- Use them for: the speaker's name during the hook; the interviewer when they speak (end the pill at the shot change back to the guest); fairness labels ("A HYPOTHETICAL", "HIS RECOLLECTION, NOT A SURVEY", "ASKED BY THE HOST").
- Times: seconds in the final video, or an anchor `[phrase, "s"|"e", offset, nth]` = start/end of a spoken phrase in the clip (lowercase, no punctuation, words as in `phrases`; `nth` 0 = first occurrence, so the hook is 0 and its repeat is 1).
- Any other event kind in `schedule` is ignored in the clean look (lint says so).

## closing / end card
`"closing": {"src": "Guest Name × Host Name · Channel"}` — one grey line on a dark card for `end_seconds` (1.5), then fade. That is the whole ending.

## headline (thumbnail only)
The `headline` block is drawn on the thumbnail, not in the video: 16:9 in a side column (`side`), 4:5 low on the frame under the face. Format in the legacy section. Pick `thumb.t` in a close-up with open eyes; `clip thumb NN <t> [L|R]` (`--tall` for the 4:5 one) remakes it.

## crops / crop_windows (optional punch-ins)
Rarely needed in the clean look (there are no text columns to keep clear). `crops` rectangles are `[w,h,x,y]` in the **1920×1080-scaled source frame** and are scaled back up to full frame (keep 16:9: e.g. 1140×641, 860×484). `crop_windows` lists source-time windows `[a,b,name]` during which that crop replaces the frame (frame-accurate; abutting windows fine). Find layout changes with `clip cuts <a> <b>`, view frames with `clip look`, then write the windows by hand. Punch-ins soften the picture — prefer full frame when it works.

## phrases / highlights (captions)
- A list of caption phrases, in order, covering **every word spoken** in the cut. They must match the speech token for token (case/punctuation free) — write "AI native" if you hear "AI native", "GPT-2" as `GPT-2`. Stutters/false starts/fillers ("um", repeated words) may be dropped.
- `|` inside a phrase forces a line break in 16:9 (≤2 lines per caption; the 4:5 version re-wraps every caption to its own width, up to 3 lines, and ignores `|` for line breaks; a phrase with a `|` that is long or slow is split into two sequential captions). Aim ≈ 28–60 characters per phrase, break at punctuation.
- Empty list → auto-built from whisper's chunk-wise transcript of the cut (`work/clips/NN/phrases_auto.json`); `glossary` (optional object `{"wrong spelling":"right"}`) fixes recurring mis-hearings. Always review before posting.
- `highlights`: substrings (case-insensitive) of phrases to colour teal (matched across the whole caption). A word is coloured only if ALL its characters are inside the match, so a word with attached punctuation (`2024,`) stays white unless the highlight includes the punctuation.

## Reading the build output
`clip build NN` runs, for 16:9 and then 4:5: plan → cut (and crop) → chunk-wise whisper (cached; the 4:5 reuses it) → captions (prints "whisper-vs-aligned deviation", median ≲0.2 s is normal) → graphics → render → thumbnail → QA. QA lines: `format` (1920×1080 or 1080×1350), `length` (25–55 s passes; target 30–45), `loudness`, `black_frames`, `captions_on_speech`, `quotes_verbatim` (+ `caption_timing_independent` with `--deep`). All must PASS for both versions. Results: `clips/NN.check.json` and `clips/NN.check_4x5.json`.

## Spanish version (`"es"` block) — only when a video should be in Spanish
`clip build NN --es` renders `NN_Title_ES.mp4` and `NN_Title_4x5_ES.mp4` (+ `.srt`, thumbnails, `First_Comment_ES.txt`) next to the English files, from the SAME spec and the SAME English audio. The voice is never translated or dubbed. Everything the viewer reads becomes Spanish. **In the clean look that means: `pills`, `phrases_es`, `highlights`, `closing.src` if it has English words, and `headline` (thumbnail).** The `cards`/`heroes`/`stats` keys in the example below are only needed for `"style": "full"`. Cuts, `tall`, schedule and anchors are shared (anchors stay English: they look up the spoken words).
```jsonc
"es": {
  "headline": {"lines": [["EL NEGOCIO DE LA IA HOY","t"],["TODO","W",110],["SE VUELVE","w",74],["COMMODITY","T",84]], "sub": "Nombre Apellido sobre el tema", "side": "L", "maxw": 600},
  "pills":   {"who": ["NOMBRE APELLIDO", "Cofundador y CEO, Empresa"], "cold": ["LA IDEA CLAVE", null]},      // same keys as the English pills
  "cards":   {"hook": {"text": "TODO LO QUE ESTÁS HACIENDO… SE VUELVE *COMMODITY* CONSTANTEMENTE", "attrib": "NOMBRE APELLIDO", "tag": "LA IDEA CLAVE, PRIMERO"}},   // same keys, same *teal* idea
  "heroes": {}, "stats": {},                                                                              // same keys as the English ones (label/foot/tag translated)
  "closing": {"main": [["VENTAJA INICIAL ","W"],["≠","T"],[" FOSO DEFENSIVO","W"]], "sub": "¿Qué estás construyendo que la próxima versión del modelo no absorba?", "src": "Invitado × Anfitrión"},
  "highlights": ["commodity", "lo siguiente"],                                                            // substrings of the Spanish captions to colour teal
  "phrases_es": ["…one Spanish caption for EACH English phrase, same order and count…"]
}
```
Rules:
- **`phrases_es[i]` is shown while English `phrases[i]` is spoken**, so the English `phrases` must be reviewed and non-empty and both lists must have the same length (lint: error). Translate by meaning, phrase by phrase; you may move a clause across the `|` but not across phrases. Keep each ≤ ~68 characters, at most one `|` (two lines). Spanish runs ~20% longer: tighten, don't abbreviate the idea away.
- Spanish quote cards are translations of the verbatim English card (QA still checks the English card against the speech). Same keys, same teal word idea, nothing added or sharpened; `…` joins stay where the English has them.
- Translate: kickers, pill sub-lines ("Co-founder & CEO" → "Cofundador y CEO"), tags ("AS HE TELLS IT" → "SEGÚN ÉL"), closing card question. Keep names, company and product names. Keep terms Spanish-speaking professionals use in English (LLM, prompt, harness) or use the common Spanish one (agentes, IA).
- Don't re-time anything: Spanish cards reveal over the English words' times.
- Review.md lists every Spanish card next to its English original; the author reads them (it is a translation by the agent, which cannot hear the audio either).
- QA and lint run with the same flag: `clip lint NN --es`, `clip check NN --es`, `clip preview NN --es`, `clip thumb NN <t> --es`. `clip build todo --es` only touches clips that have an `"es"` block. Cost ≈ one extra build per clip (about 3 min; whisper is cached).

---

# Legacy: `"style": "full"` (16:9 only)
Everything below applies only to specs with `"style": "full"`: the earlier look with an animated headline, quote cards, heroes, stat blocks and a 4–5.5 s closing card (`card_seconds`). The clean look replaced it; use this only if needed for the old graphics on a specific clip. The 4:5 version ignores it.

## headline
`{"lines":[["KICKER","t"],["BIG","W",210],["MED","w",84],["TEAL","T",130]], "sub":"Speaker on topic", "sub_style":"white", "side":"R", "maxw":560, "y0":null}`
Line styles: `t` tiny tracked kicker · `W` big white · `w` medium white · `T` big teal; optional 3rd value = max font size (auto-fits to `maxw`). `sub_style:"white"` makes the sub-line bold white instead of grey. `side` L|R = which column.

## cards (verbatim quotes)
`{"key":{"text":"SO MANY PEOPLE JUST *SHRUGGED* AND THEY JUST *DISMISSED IT.*","attrib":"DARIO AMODEI","tag":"optional line above","maxw":600,"size":64,"maxlines":5}}`
- `text`: UPPERCASE, `*teal*` marks, `|` forced line break, `…` joins two separate quoted fragments (each checked separately). Drop stutters but add no words.
- `maxw` ≈ 560–680 (column width), `size` = max font size (auto-shrinks to fit `maxlines`).

## heroes (slam)
`{"key":{"pre":["DO YOU THEN WANT TO TELL","YOUR USER THAT THEY'RE WRONG?"],"lines":[["NO,","T",210],["YOU DON'T.”","W",112]],"attrib":"DANIELA AMODEI","maxw":620}}` — optional small `pre` lines, then big stacked lines (`T` teal / `W` white, max size); `tag` optional. Verbatim words only.

## stats
`{"key":{"tag":"HIS RECOLLECTION, NOT A SURVEY","big":"~10%","big_color":"T","label":"SHARED HIS REACTION","states":["T","D","D","D","D","D","D","D","D","D"],"foot":"of the people around him","maxw":620}}` — `states`: 10 blocks, `T` teal, `W` white, `D` dim.

## closing
`{"main":[["IDEA A ","W"],["≠","T"],[" IDEA B","W"]],"sub":"One question or lesson.","src":"Speaker × Interviewer"}`

## schedule (what appears when)
List of events; each has `k` (kind), `t_in`, `t_out`, optional `side` (L|R), `y`, `fi`/`fo` (fade seconds):
- `{"k":"headline","t_in":0.17,"t_out":4.5}`
- `{"k":"pill","key":"who","t_in":4.9,"t_out":9.6,"side":"R","y":130}`
- `{"k":"card","key":"shrug","t_in":["so many people","s",-0.15],"t_out":["dismissed it","e",1.0],"side":"R","y":390}`
- `{"k":"hero","key":"nodont","t_in":[...],"t_out":[...],"side":"L","y":250,"hero_t":[["no","s",-0.05,0],["you dont","s",-0.05]]}` — `hero_t`: when each big line pops
- `{"k":"stat","key":"s10","t_in":[...],"t_out":[...],"side":"R","y":500}`

**Times** are either a number (seconds in the *final* video) or an **anchor** `[phrase, "s"|"e", offset_seconds, nth]`: the start (`s`) or end (`e`) of a spoken phrase **in the clip**, plus an offset. `phrase`: lowercase, no punctuation, words as actually spoken in the cut (it is looked up in `work/clips/NN/tokens.json`, which is built from your `phrases`). `nth` (default 0) picks the n-th occurrence. A card whose `t_in` is an anchor reveals its lines word-synchronously with the speech. Headline: `t_in` 0.17, `t_out` 3.9–5.0. Cards: `t_in` ≈ phrase start −0.1, `t_out` ≈ phrase end +1.0…1.6.
A missing anchor stops the build with the exact phrase — fix the spec, rebuild.

