#!/usr/bin/env bash
# describe-visual-media / video-describe-for-blind
# Extract frames, audio, and a grid collage from a video so the agent can SEE it
# (by VIEWING the local collage file directly) and narrate it for visually-impaired users.
#
# Usage: run.sh <path-to-video> [target_frames]
#   default target_frames = 24  (evenly spread across the WHOLE video)
#   You may still pass a number to force more/less coverage.
#
# Frame sampling is ADAPTIVE: instead of a fixed fps, the script aims for a target
# number of frames spread evenly over the full duration, so:
#   - a 5s clip  -> ~1 frame/sec (dense, nothing missed)
#   - a 60s clip -> ~1 frame every 2.5s (full coverage, still a readable collage)
#   - a 3s clip  -> a handful of frames, still spread across it
# This fixes the old fixed-fps behaviour that under-sampled long videos and produced
# a giant unreadable collage.
#
# Outputs (in incoming_files/, so paths are chat-safe):
#   _vd_grid.jpg      -> collage of all frames (VIEW THIS local file directly)
#   _vd_audio.mp3     -> extracted audio (transcribe with transcribe_audio tool)
#   _vd_f_XX.jpg      -> individual frames
# Prints a JSON-ish summary the agent reads.
#
# ENVIRONMENT-RESILIENT: ffmpeg is resolved in this priority order:
#   1. system ffmpeg (if on PATH)
#   2. imageio-ffmpeg's bundled binary (pip-installed at runtime, no system deps)
#   3. fail loudly with a clear, agent-readable error (which the agent relays to the user)

set -euo pipefail

VIDEO="${1:?ERROR: usage: run.sh <video> [target_frames]}"
TARGET_FRAMES="${2:-24}"

if [ ! -f "$VIDEO" ]; then
  echo "ERROR: video not found: $VIDEO" >&2
  echo "VD_STATUS: failed reason=video_not_found" >&2
  exit 1
fi

# --- resolve ffmpeg: system first, else imageio-ffmpeg's bundled binary ---
FFMPEG_BIN=""
if command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG_BIN="$(command -v ffmpeg)"
else
  if ! python3 -c "import imageio_ffmpeg" >/dev/null 2>&1; then
    pip install --quiet imageio-ffmpeg >/dev/null 2>&1 || true
  fi
  FFMPEG_BIN="$(python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || true)"
fi

if [ -z "$FFMPEG_BIN" ] || [ ! -x "$FFMPEG_BIN" ]; then
  echo "ERROR: no ffmpeg available (system ffmpeg missing and imageio-ffmpeg fallback failed)." >&2
  echo "VD_STATUS: failed reason=no_ffmpeg" >&2
  exit 2
fi

# ensure Pillow is present for the collage step
if ! python3 -c "import PIL" >/dev/null 2>&1; then
  pip install --quiet Pillow >/dev/null 2>&1 || true
fi

OUTDIR="incoming_files"
mkdir -p "$OUTDIR"
WORK="$(mktemp -d)"

# --- probe (imageio-ffmpeg has no ffprobe; derive metadata via ffmpeg stderr) ---
PROBE="$("$FFMPEG_BIN" -hide_banner -i "$VIDEO" 2>&1 || true)"
DUR="$(printf '%s\n' "$PROBE" | grep -oE 'Duration: [0-9:.]+' | head -1 | sed 's/Duration: //' || echo '?')"
DIMS="$(printf '%s\n' "$PROBE" | grep -oE '[0-9]{2,5}x[0-9]{2,5}' | head -1 || echo '?')"
if printf '%s\n' "$PROBE" | grep -q 'Audio:'; then HAS_AUDIO="yes"; else HAS_AUDIO=""; fi

# --- compute duration in seconds from "Duration: HH:MM:SS.xx" ---
DUR_SECS="$(printf '%s\n' "$DUR" | awk -F: '{
  if (NF==3) { print ($1*3600)+($2*60)+$3 }
  else if (NF==2) { print ($1*60)+$2 }
  else { print $1 }
}' 2>/dev/null || echo 0)"
# sanitize (strip anything non-numeric that awk may keep)
DUR_SECS="$(printf '%s' "$DUR_SECS" | grep -oE '^[0-9]+(\.[0-9]+)?' || echo 0)"

# --- ADAPTIVE fps: aim for TARGET_FRAMES spread over the whole video ---
# fps = target_frames / duration, clamped to [~0.3 .. 2] so we never over/under-sample wildly.
# If duration is unknown or tiny, fall back to fps=1.
FPS="$(python3 - "$DUR_SECS" "$TARGET_FRAMES" <<'PY'
import sys
dur = float(sys.argv[1] or 0)
target = float(sys.argv[2] or 24)
if dur <= 0:
    print("1"); raise SystemExit
fps = target / dur
# clamp: at most 2 fps (fast action), at least 1 frame / ~3.3s so long videos stay covered
if fps > 2: fps = 2.0
if fps < 0.3: fps = 0.3
print(f"{fps:.4f}")
PY
)"

# --- clean old outputs (idempotent) ---
rm -f "$OUTDIR"/_vd_f_*.jpg "$OUTDIR"/_vd_grid.jpg "$OUTDIR"/_vd_audio.mp3 2>/dev/null || true

# --- extract frames at the adaptive fps ---
if ! "$FFMPEG_BIN" -hide_banner -loglevel error -i "$VIDEO" -vf "fps=${FPS}" "$WORK/f_%03d.jpg"; then
  echo "ERROR: frame extraction failed (corrupt or unsupported video?)." >&2
  echo "VD_STATUS: failed reason=frame_extraction_failed" >&2
  rm -rf "$WORK"
  exit 3
fi

# --- hard cap at TARGET_FRAMES: if ffmpeg produced more, keep an evenly-spread subset ---
mapfile -t ALLF < <(ls "$WORK"/f_*.jpg 2>/dev/null | sort)
TOTAL=${#ALLF[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "ERROR: no frames produced, video may be empty or unreadable." >&2
  echo "VD_STATUS: failed reason=no_frames" >&2
  rm -rf "$WORK"
  exit 4
fi

n=0
if [ "$TOTAL" -le "$TARGET_FRAMES" ]; then
  for f in "${ALLF[@]}"; do
    n=$((n+1))
    cp "$f" "$OUTDIR/_vd_f_$(printf '%02d' $n).jpg"
  done
else
  # evenly-spread selection of TARGET_FRAMES out of TOTAL
  mapfile -t PICK < <(python3 - "$TOTAL" "$TARGET_FRAMES" <<'PY'
import sys
total=int(sys.argv[1]); target=int(sys.argv[2])
# pick target indices spread across [0, total-1] inclusive
idx=[round(i*(total-1)/(target-1)) for i in range(target)] if target>1 else [0]
seen=set(); out=[]
for i in idx:
    if i not in seen:
        seen.add(i); out.append(i)
print("\n".join(str(i) for i in out))
PY
)
  for i in "${PICK[@]}"; do
    n=$((n+1))
    cp "${ALLF[$i]}" "$OUTDIR/_vd_f_$(printf '%02d' $n).jpg"
  done
fi
NFRAMES=$n

# --- extract audio if present ---
AUDIO_OUT="none"
if [ -n "${HAS_AUDIO:-}" ]; then
  if "$FFMPEG_BIN" -hide_banner -loglevel error -i "$VIDEO" -vn -acodec libmp3lame -q:a 4 "$OUTDIR/_vd_audio.mp3" 2>/dev/null; then
    AUDIO_OUT="$OUTDIR/_vd_audio.mp3"
  fi
fi

# --- build collage grid (up to 6 columns so long videos stay readable) ---
python3 - "$OUTDIR" "$OUTDIR/_vd_grid.jpg" "$NFRAMES" <<'PY'
import sys, glob, os
try:
    from PIL import Image
except Exception:
    print("VD_STATUS: failed reason=no_pillow", file=sys.stderr)
    sys.exit(5)
outdir, out, nframes = sys.argv[1], sys.argv[2], int(sys.argv[3])
files = sorted(glob.glob(os.path.join(outdir, "_vd_f_*.jpg")))
if not files:
    sys.exit(0)
imgs = [Image.open(f).convert("RGB") for f in files]
w = 240
small = []
for im in imgs:
    r = w / im.width
    small.append(im.resize((w, int(im.height * r))))
# scale columns to frame count: few frames -> 4 cols, many -> up to 6
cols = 4 if len(small) <= 12 else 6
rows = (len(small) + cols - 1) // cols
cw, ch = w, small[0].height
grid = Image.new("RGB", (cols*cw, rows*ch), (15,15,15))
for i, im in enumerate(small):
    grid.paste(im, ((i % cols)*cw, (i // cols)*ch))
grid.save(out, quality=88)
PY

rm -rf "$WORK"

echo "==== DESCRIBE-VISUAL-MEDIA ===="
echo "ffmpeg:       $FFMPEG_BIN"
echo "duration:     $DUR  (${DUR_SECS}s)"
echo "dimensions:   $DIMS"
echo "frames:       $NFRAMES (adaptive fps=$FPS, target=$TARGET_FRAMES)"
echo "grid:         $OUTDIR/_vd_grid.jpg"
echo "audio:        $AUDIO_OUT"
echo "frames_glob:  $OUTDIR/_vd_f_*.jpg"
echo "VD_STATUS:    ok frames=$NFRAMES audio=$AUDIO_OUT"
echo "==============================="
echo ""
echo "NEXT STEPS FOR THE AGENT:"
echo "1. SEE the video by VIEWING the local collage file directly:"
echo "      view the image file  $OUTDIR/_vd_grid.jpg  with your built-in image view."
echo "   For one moment in detail, view a single  $OUTDIR/_vd_f_XX.jpg  the same way."
echo "   NEVER use the browser (browserbase_navigate/browserbase_screenshot) to view it on"
echo "   WhatsApp, and NEVER upload_file / send_image the collage or frames - each of those"
echo "   leaks an image BUBBLE into the chat. The user may be blind and must receive ONLY a"
echo "   text message + a voice message. Viewing a LOCAL file creates no chat bubble."
echo "2. If audio exists: transcribe_audio($OUTDIR/_vd_audio.mp3)"
echo "3. JUDGE the content yourself and pick the mode (do NOT ask the user what to do if it is"
echo "   obvious): hazard/safety if anything looks unsafe, shopping list from a fridge, guide-dog"
echo "   for a pet, otherwise a short general description. Only ask ONE question if truly ambiguous."
echo "4. Compose the description, then deliver VOICE-FIRST on WhatsApp:"
echo "     send the full description as a send_whatsapp_voice_message voice note (this is the"
echo "     mandatory answer), and END the voice by asking: 'want this as a text message too?'"
echo "     Then STOP. Only if the user replies yes, send the SAME content as a text message."
echo "     Do NOT send text automatically or before the voice. (Plain in-app chat: text only.)"
echo "5. If VD_STATUS=failed at any point: tell the user (in their language, no jargon) that"
echo "   the video couldn't be processed and give a short retake/resend instruction."