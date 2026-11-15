# LESSONS — mistakes already made and quirks already solved

Written down while building and using the pipeline, so they are not repeated. Grouped by where they bite.

## Editorial (what the clip says)
- **Verify the speaker on screen, not just in the transcript.** A brief attributed a passage to one co-founder; the footage showed the other. Captions, descriptions and briefs can all be wrong → `clip look`, then match lips and gestures to the voice.
- **Check the sentence after your end point** (and the one before the start). In one clip the next sentence began 0.07 s later and reversed the meaning.
- **Framing words can belong to the interviewer.** If a key phrase came from the question, the post and graphics must say so. Never attach a paraphrase to a speaker inside quotation marks.
- **Recollections are not data.** "Maybe 10% of people…" is labelled as a recollection, hypotheticals are labelled as such, and the speaker's stake is disclosed when relevant.
- **A hook obeys the same fairness rules as the clip.** It is the speaker's verbatim, complete sentence, and must keep its meaning out of context (check the rest of the passage for a hedge). Never take the hook from the interviewer, and never let the post say more than the clip.
- **Don't open on the interviewer.** A clip that spent its first ten seconds on the host's question lost the viewer before the point.
- Each post stands alone: no "Part 1/2".

## Cutting
- Cut inside real pauses found from audio energy (`clip snap` / `clip pauses`), not from caption times: ASR word times drift ±0.3–0.6 s around pauses. A joined cut needs ≈0.2 s of quiet on both sides; shorten the dissolve (`x` 2–3) when the speaker barely pauses.
- **A dip in the audio is not always a gap between words.** A 0.09 s dip inside "the thing" looked like the end of a sentence; the cut lost a word and QA still passed, because QA cannot know a word is missing. After every build, read the first and last words of each segment in `work/clips/NN/words_final.json` against the sentence you meant to cut.
- `clip pauses` can miss a real pause when room tone is high. Always read `phrases_auto.json` after the first build: the first line must be the complete hook sentence.
- A speaker who continues without a pause cannot be cut cleanly there: end on a natural landing or choose another point.
- Interviewer **reaction cutaways** cannot be removed: hold the guest's last frame (`vend`), accept it mid-clip, or pick different footage.
- Split-screen layouts, picture-in-picture and wide two-shots: look at frames first (`clip cuts`, `clip look`). Crops are source-specific.
- Re-cutting an old clip: create a new spec number instead of editing the old one, so the published version is never overwritten before the new one is approved.

## Captions and graphics
- Auto-built captions are a first draft. Whisper invents tiny words ("Thank you.") in very short chunks and mishears AI vocabulary; add recurring ones to `glossary.json` (whisper hint) or the spec's `glossary` (caption fixes), and read every caption.
- Caption timing uses an energy-constrained alignment, validated against an independent re-transcription (median deviation 0.11–0.17 s). **Always read the "whisper-vs-aligned deviation" line: p95 above ~1.5 s means captions are misplaced.** An early version capped tokens per speech run at 45, which pushed captions up to 10 s early on long unbroken speech; the cap is now 130.
- Whisper can hallucinate where a chunk straddles an edit join. If deviation is bad, inspect `words_final.json` and correct the cached chunk.
- Quote cards (legacy look) must be verbatim and are machine-checked against the cut's own transcript and the platform's captions. YouTube auto-captions drop words at speaker changes, so a quote ending there fails lint: end it earlier.
- Name pills at the top of the frame sat on heads in close-ups and labelled the wrong person in a two-shot. Lower-thirds on the speaker's side fixed both.
- Pillow renders all text (the available ffmpeg build has no drawtext/libass), so overlays are an RGBA PNG sequence composited by ffmpeg.
- Preview (`clip preview NN`) before declaring done: typical collisions are pills overlapping captions and crops that lose the speaker's head.

## Process and tooling
- **A format decision is not done until a clip is rebuilt in it and looked at.** A new format was written down and then never built; the next batch still went out in the old one.
- **Order of work matters more than speed of the tools.** One early job took ~4 hours, of which ~85% was waiting for builds: every rebuild re-ran whisper on identical audio (now cached by audio hash), spec mistakes only surfaced after the slow steps (now `clip lint` runs first, in about a second), and two whisper models in parallel on an 8 GB machine thrashed memory (now one heavy job at a time, the rest queue behind a lock).
- Whisper runs chunk-wise (one call per pause-delimited chunk). beam 1 + 4 threads was ~2.9× faster than beam 5 + 8 threads on an M1 with the same real words. Packing chunks into shared windows was tried and rejected: no faster, and word times moved by up to 3 s.
- Write all specs → `clip lint all` → one background `clip build todo` queue; write the posts while it runs. `--deep` QA is a second whisper pass: use it once, serially, only when something looks off.
- Subtitle download asks only for `en` / `en-orig`: asking for `en.*` pulls auto-translated tracks and gets rate-limited, which used to abort the whole download. Captions are best-effort; the video download never depends on them.
- The tool cannot hear audio. It lists every join in `Review.md` so a human does one targeted listen.
- Errors crept in when drafts were edited by hand after the checks ran (a misspelled host name, a wrong model name, a paraphrase inside quotation marks). The final text should be pasted back and re-checked against the transcript.
- Disk: a job is 1–2 GB while working; `clip clean` leaves ~30 MB per finished post.
