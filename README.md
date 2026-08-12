# Facebook AI Studio

A small Python automation project that generates vertical Arabic episode artifacts from a script. The current pipeline creates an Arabic voice-over with `edge-tts`, renders it over a 1080×1920 background, and stores the resulting MP4 under `storage/autopilot/`.

> The project currently generates local video artifacts only. It does not publish to Facebook and it does not contain Facebook API credentials.

## Requirements

Use Python 3.11 or newer and install the pinned runtime dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

MoviePy relies on FFmpeg through its normal Python dependency chain. On a local machine, make sure FFmpeg is available if your MoviePy installation does not provide a usable binary.

## Generate an episode

The default command uses the built-in Arabic script and writes `storage/autopilot/EP01.mp4`:

```bash
python core/autopilot.py
```

Use a UTF-8 text file for a custom script:

```bash
python core/autopilot.py \
  --script-file scripts/episode-02.txt \
  --voice ar-EG-ShakirNeural \
  --episode-name EP02 \
  --background 10,10,10
```

Run a configuration check without calling `edge-tts` or rendering a video:

```bash
python core/autopilot.py --dry-run --episode-name smoke-test
```

The generated MP3 is temporary by default and is removed after the MP4 is written. Add `--keep-audio` when the audio artifact is needed.

## Environment variables

Command-line flags take precedence over environment variables. The supported variables are shown below.

| Variable | Purpose | Default |
| --- | --- | --- |
| `AUTOPILOT_SCRIPT` | Script text when `--script-file` is not provided | Built-in Arabic episode |
| `AUTOPILOT_VOICE` | `edge-tts` voice name | `ar-EG-ShakirNeural` |
| `AUTOPILOT_OUTPUT_DIR` | Artifact directory | `storage/autopilot` |
| `AUTOPILOT_EPISODE_NAME` | Output filename stem | `EP01` |
| `AUTOPILOT_BACKGROUND` | `#RRGGBB` or `R,G,B` background | `10,10,10` |
| `AUTOPILOT_FPS` | Output frame rate | `24` |
| `AUTOPILOT_TTS_RETRIES` | Speech-synthesis attempts for transient network errors | `3` |

Do not commit credentials or private tokens. Keep local secrets in an untracked `.env` file only if a future integration requires them, and add the corresponding variable names to `.env.example` without real values.

## Tests

The unit tests validate configuration parsing and output path handling without making network calls or generating media:

```bash
python -m unittest discover -s tests -v
```

## GitHub Actions

`.github/workflows/autopilot.yml` runs at 06:00, 12:00, 18:00, and 21:00 UTC, and can also be started manually with **Run workflow**. Each run installs `requirements.txt`; the generator retries transient speech-synthesis failures up to three times by default; and the workflow uploads the MP4 as an artifact retained for seven days. GitHub Actions cron uses UTC; adjust the schedule if the desired local time changes with daylight saving time.

## Project layout

```text
core/autopilot.py          # CLI, speech generation, and video rendering
requirements.txt           # pinned runtime dependencies
storage/autopilot/         # generated artifacts; media is not committed
.github/workflows/         # scheduled CI workflow
tests/                     # fast configuration tests
```
