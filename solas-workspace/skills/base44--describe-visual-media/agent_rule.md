# Describe Visual Media, agent rules

This file stops the agent from re-implementing the tested pipeline script. Capable models
"helpfully" rewrite the ffmpeg/frame-extraction inline and get it subtly wrong (wrong fps,
missing the collage step, breaking the chat-safe paths).

## Always check the skill before acting

For ANY describe-visual-media task:
1. Read `describe-visual-media/SKILL.md` first.
2. Follow the documented procedure exactly, do NOT write inline code that duplicates
   `scripts/run.sh`.

## Video requests specifically

When the user sends a video to describe:
- DO NOT write a new inline ffmpeg / frame-extraction / collage script.
- DO run:
  ```bash
  bash describe-visual-media/scripts/run.sh <video-path> [fps]
  ```
  (pass a target frame count as the 2nd arg for more/less coverage; default 24, spread over the
  whole video). Then SEE the frames by VIEWING the local collage file `incoming_files/_vd_grid.jpg`
  directly with your built-in image view, that is how you SEE the frames. NEVER open it in the
  browser (`browserbase_navigate` / `browserbase_screenshot`) on WhatsApp and NEVER `upload_file`
  (public) or `send_image` the collage/frames, each of those leaks an image bubble to the user,
  who may be blind and must receive ONLY voice + text. Viewing a LOCAL file creates no bubble.
- Audio: use the built-in `transcribe_audio` on `incoming_files/_vd_audio.mp3`. Don't shell
  out to a custom transcription.

## Script exists, don't recreate it

- `scripts/run.sh`, extracts frames at the given fps, extracts audio to mp3, and builds a
  4-column collage grid into `incoming_files/`. Call it for every video. It is idempotent
  (cleans old `_vd_*` outputs each run).

If the frames look wrong (too few, too blurry), the fix is to **re-run the script with a
different fps**, not to write manual ffmpeg calls.

## Delivery is not optional

Always deliver BOTH, the text FIRST as its own standalone chat message, THEN the WhatsApp
voice message (SKILL.md critical rule 3). The text must actually go out as a real, separate
text message the user can read on a braille display and forward/share, do NOT skip it
"because the voice already said it", and do NOT fold it into a tool call. If the text did not
appear as its own message, resend it as plain text.

## Animals: always give a body/health readout

For ANY animal (guide-dog mode or not), ALWAYS include a short visible body/health readout
automatically, coat condition, body weight, posture, alertness, visible eyes/nose, plus any
visible injury, even if the user did not ask. End it with a one-line plain-language caveat
that this is a visual impression only, not a vet exam. Never omit the health readout for a pet.

## Never send the collage or frames back

The collage (`_vd_grid.jpg`) and frames (`_vd_f_*.jpg`) are INTERNAL sight tools. NEVER
`send_image` or `upload_file` them, and NEVER view them via the browser
(`browserbase_navigate` / `browserbase_screenshot`) on WhatsApp, each of those leaks an image
bubble. View them ONLY by opening the LOCAL file directly with your built-in image view. The user
must receive ONLY the text and the voice message, zero image bubbles.


## Judge the content yourself, almost never ask

The user should not have to tell you what to do with the media. Decide yourself:
- **Safety is an ALWAYS-ON scan on every photo/video.** Actively look for hazards (something on
  the floor in a walking path, a tipped chair, cables, spills, sharp/hot/electrical risks, a
  blocked exit). If you see a real hazard, LEAD with it and say there is a risk, even if the user
  only said "what's this?". Never ask "do you want a safety check?", just give it.
- If nothing is unsafe and nothing obvious needs doing, give a short warm general description.
  Don't manufacture danger for an innocent scene.
- Ask ONE question only in a genuine edge case where modes diverge a lot. This is rare.
