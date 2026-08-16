# Describe Visual Media, worked examples

Four end-to-end walkthroughs covering the gnarly cases: a task-focused video, a safety
photo, a sensitive legal video, and a directed-retake. These show the full flow, not just
the happy path.

---

## Example 1, shopping (video, task stated)

**User (WhatsApp, voice+video):** "I filmed my fridge, make me a shopping list."

**Agent (internal):**
1. Intent = `shopping` (explicit). No question needed.
2. `bash describe-visual-media/scripts/run.sh incoming_files/fridge.mp4`
3. VIEW the local file `incoming_files/_vd_grid.jpg` directly (built-in image view) → sees shelves. Never browser-screenshot it on WhatsApp, never upload_file/send_image it (image bubbles).
4. No meaningful audio → skip transcription.
5. Compose shopping mode: inventory + what's low + list.

**Voice delivered (the answer, spoken):**
> In the fridge I saw: milk (almost empty, only a thin layer left at the bottom), 3 eggs in a
> carton of 12, an opened pack of yellow cheese, a full jar of pickles, and a bag of vegetables
> with 2 tomatoes and one carrot. The bottom shelf is nearly empty. A suggested shopping list:
> milk, eggs, and fresh tomatoes or vegetables. Would you like me to send this to you as a text
> message too?

**User:** "Yes."

**Text delivered (only after the user asked):**
> Shopping list:
> - Milk (about to run out)
> - Eggs (only 3 left)
> - Tomatoes / fresh vegetables

**CTA:** "Want me to save this as a reminder, or send it to someone?"

---

## Example 2, safety (photo, intent obvious, assumption stated)

**User:** sends a photo of a living room, writes nothing.

**Agent (internal):**
1. No task stated, but content is a room → likely `safety` OR `general`. Borderline.
2. Content alone isn't unambiguous (could just want a description) → state assumption, proceed
   with `general` but flag hazards (the always-on safety scan applies in every mode).

**Voice delivered (the answer, spoken):**
> A living room. In the center a gray sofa, on the left a low wooden coffee table, on the right an
> armchair. On the floor in front of the sofa there's a rug, and one corner of it is folded up, a
> trip hazard. An electrical cable runs from the left wall to under the table. Would you like me to
> send this to you as a text message too?

**CTA (spoken, after the offer):** "And want me to draft a message to report the rug and cable?"

---

## Example 3, legal (video, sensitive, ambiguity handled)

**User (a lawyer assisting a blind client):** sends an accident clip, "What's happening here?"

**Agent (internal):**
1. "What's happening here" + accident content → could be `general` or `legal`. The stakes
   (evidence) make it worth ONE question.
2. **Ask one question:** "Is this for a factual record (as evidence), or a general description?"
   → user: "Factual."
3. Run script (pass a higher target frame count for fast/long action), VIEW the local collage file directly, transcribe audio.
4. Compose `legal` mode: neutral, chronological, read plates/signals, flag camera limits.

**Voice delivered (the answer, spoken):**
> Factual description, in order. At the start of the clip: a silver car travels in the right lane,
> speed appears steady. In the background a green traffic light, clearly visible. About 3 seconds
> in: a dark car enters the intersection from the left. The moment of contact itself is blurry and
> out of full focus. At the end: both cars are stopped, the silver one has damage to its right
> front. The dark car's license plate is not clearly legible. Note: it cannot be determined from
> this angle who ran a red light. Would you like me to send this to you as a text message too?

**User (a legal record, so likely):** "Yes, send the text."

**Text delivered (only after the request):** the same factual, dated summary, so it can be
forwarded and kept as evidence.

**CTA:** "Want me to write this up as a dated, neutral summary you can forward?"

---

## What these examples demonstrate
- **Intent drives output:** the same "what's here?" yields a list, a hazard scan, or a neutral
  record depending on the task.
- **Ask-one-question** only when genuinely ambiguous and stakes justify it (Example 3), not always.
- **Never invent:** Example 3 explicitly flags the blurry impact and unreadable plate instead
  of guessing fault.
- **Voice-first + a closing "want this as text too?" offer**, in every example. Text is sent only when the user says yes.


---

## Example 4, directed retake, in the right language

**User (English):** sends a fridge clip and says: "Do I have lettuce, pepper, cucumber, apple and banana?"

**Agent:**
- Sees only part of the fridge.
- Can confirm some visible items, but not all requested ones.
- Because the question was in English, the reply is in English. (The reply always matches the
  user's language, whatever it is.) Any label inside the fridge is still read in its original
  language as-is.

**Voice delivered (the answer, spoken):**
> I can clearly see a pepper and a few yogurt cups, but I can't confirm whether you have lettuce,
> cucumber, apple or banana. Please film the bottom drawers and the fridge door again, slowly, and
> hold each area for two to three seconds. Would you like me to send these instructions to you as a
> text message too?

**User:** "Yes."

**Text delivered (only after the request):**
> I could confirm: one pepper, a few yogurt cups. Not confirmed: lettuce, cucumber, apple, banana.
> Please refilm the bottom drawers and the fridge door slowly, holding each area 2 to 3 seconds.
