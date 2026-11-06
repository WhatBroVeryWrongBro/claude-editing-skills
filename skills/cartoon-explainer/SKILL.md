---
name: cartoon-explainer
description: Make a narrated 2D cartoon explainer Short (9:16, ~45-60s) from a topic. ElevenLabs does the voice; Claude Code writes the script, draws every scene as SVG, adds outlined captions, SFX and music, and renders it. Use for /cartoon-explainer or "make a cartoon explainer / what-if short about X".
---

# /cartoon-explainer

Recreates the "What if...?" cartoon-explainer Short format: flat vector scenes with a simple white-headed character, a cut or whip-pan every 2-4 seconds, a fast conversational voiceover, bold white captions with a thick black outline, pops/whooshes, and a closing question that drives comments.

**Division of labour:** the voice is ElevenLabs. Everything else (script, scene art, captions, camera moves, transitions, SFX, music, mix, render) is produced by Claude Code with the files in this folder. Nothing else needs an API.

## Workflow

1. **Write the script** (ask for the topic if none given). Target 130-160 words, 12-16 scenes, one short sentence or two per scene:
   - Hook (scenes 1-2, first 3s): a shocking "what if" with a physical visual.
   - Core (to ~60%): the mechanism through visual metaphors, one idea per scene.
   - Twist (next 20%): the real-world catch or absurd detail ("100% fatal fine print").
   - Closer: a direct question to the viewer, nothing after it.
2. **Draw each scene** as `scenes/NN.svg`, viewBox `0 0 1080 1920`. Keep the action in y 300-1250; the caption sits at y~1330 and platform UI covers the top 220 and bottom 420 px. Use the built-in character with `<use href="#hero-happy|scared|think|dead" x= y= width= height=>` (about 300x700 for a full body, larger for a close-up). Draw props and backgrounds as flat shapes with an 8px `#111` stroke; warm pastels for the real world, purple/neon grid for digital scenes. Make one visual pun per scene (slicing a brain = deli slicer). See `example/scenes/` for three.
3. **Write `spec.json`** (see `example/spec.json`): per scene `svg`, `text` (exact narration), `camera` (`push`, `pull`, `pan-left`, `pan-right`, `still`), `transition` (`whip` default, `zoom`, `cut`) and `sfx` such as `"pop@0.4"` (seconds into the scene; built-ins: pop, beep, squish, thud, whoosh, ding; whooshes are added to whips automatically).
4. **Voice with ElevenLabs.**
   - With the ElevenLabs connector in Claude Code: `creative_list_voices`, pick a warm, energetic, conversational narrator (say which), then `creative_generate_speech` once per scene's `text`. Save each take as `voice/scene-NN.mp3`. Use one flow and the same voice for every scene so the narration is consistent. Do not repeat a generation call to retry; it costs credits.
   - With an API key instead: `ELEVENLABS_API_KEY=... python3 voice.py spec.json [--voice VOICE_ID]` writes the mp3s plus `scene-NN.words.json` with exact word timings.
5. **Build:** `python3 /path/to/skills/cartoon-explainer/build.py spec.json`. Scene length is the audio length plus `pad` (0.3s). Without word timings, caption words are spread by letter count, which is close enough for one-sentence scenes. Without audio at all it uses `dur`/word count, which makes a silent draft for checking the art. `--prepare-only` writes the editable HyperFrames composition and skips rendering.
6. **Check** the first frame (hook readable at once), one mid scene and the last frame; confirm the caption never covers a face or the key prop and the mix keeps the voice on top. Fix the SVG or spec and rebuild.

Requirements are the same as the other skills: ffmpeg/ffprobe, Node.js 22+ (HyperFrames 0.8.214 and pinned GSAP 3.15.0 are fetched on first run), Python 3.9+. Captions use the bundled Archivo Black. Music and SFX are synthesized by ffmpeg; replace `music` with your own track by dropping it in and mixing it over the output if you want something richer.
