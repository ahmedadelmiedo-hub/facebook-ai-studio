"""Embed precomputed MP3 segments into a private Kaggle notebook package.

The Kaggle kernels API may omit arbitrary sidecar files from a pushed kernel package.
Embedding the already-generated audio bytes in a code cell makes the transfer explicit;
no API keys are embedded.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    notebook = json.loads(args.notebook.read_text(encoding="utf-8"))
    audio_files = sorted(args.audio_dir.glob("*.mp3"))
    if not audio_files:
        raise SystemExit(f"No MP3 segments found in {args.audio_dir}")
    payload = {
        path.name: base64.b64encode(path.read_bytes()).decode("ascii")
        for path in audio_files
    }
    source = [
        "import base64\n",
        "from pathlib import Path\n",
        f"_audio_payload = {json.dumps(payload, ensure_ascii=True)}\n",
        "_audio_dir = Path('/kaggle/working/audio_segments')\n",
        "_audio_dir.mkdir(parents=True, exist_ok=True)\n",
        "for _name, _encoded in _audio_payload.items():\n",
        "    (_audio_dir / _name).write_bytes(base64.b64decode(_encoded))\n",
        "print('Embedded audio segments restored:', len(_audio_payload))\n",
        "del _audio_payload, _encoded, _name, _audio_dir\n",
    ]
    cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }
    cells = notebook.get("cells", [])
    insert_at = next(
        (index + 1 for index, item in enumerate(cells)
         if item.get("cell_type") == "code" and "config_path = Path" in "".join(item.get("source", []))),
        1,
    )
    cells.insert(insert_at, cell)
    notebook["cells"] = cells
    args.notebook.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Embedded {len(audio_files)} audio segment(s) into {args.notebook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
