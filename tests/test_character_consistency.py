import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.character_consistency import (
    build_prompt,
    build_scene_manifest,
    generation_key,
    load_character_bible,
)


CHARACTER_FILE = Path(__file__).parents[1] / "content" / "characters" / "nour-podcast-host-v1.json"


class CharacterConsistencyTests(unittest.TestCase):
    def test_character_bible_loads_required_identity(self):
        character = load_character_bible(CHARACTER_FILE)
        self.assertEqual(character.character_id, "podcast_host_nour_v1")
        self.assertEqual(character.version, 1)
        self.assertIn("nour-master-v1.png", character.reference_image)

    def test_prompt_keeps_identity_and_adds_scene(self):
        character = load_character_bible(CHARACTER_FILE)
        positive, negative = build_prompt(
            character,
            "Nour examines a damaged cassette in an archive room",
            "over-the-shoulder medium shot",
        )
        self.assertIn("short dark curly bob", positive)
        self.assertIn("mustard-yellow blazer", positive)
        self.assertIn("damaged cassette", positive)
        self.assertIn("different person", negative)
        self.assertIn("over-the-shoulder", positive)

    def test_manifest_key_is_deterministic(self):
        character = load_character_bible(CHARACTER_FILE)
        first = build_scene_manifest(
            character,
            "Nour sits in the studio",
            "medium shot",
            seed=123,
        )
        second = build_scene_manifest(
            character,
            "Nour sits in the studio",
            "medium shot",
            seed=123,
        )
        self.assertEqual(first["generation_key"], second["generation_key"])
        self.assertEqual(first["status"], "planned")
        self.assertIn("visual-cache", first["cache_path"])

    def test_cli_data_is_json_serializable(self):
        character = load_character_bible(CHARACTER_FILE)
        manifest = build_scene_manifest(character, "studio intro", "medium shot")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "scene.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["character_id"], character.character_id)

    def test_generation_key_changes_when_scene_changes(self):
        first = generation_key({"scene": "a", "seed": 1})
        second = generation_key({"scene": "b", "seed": 1})
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
