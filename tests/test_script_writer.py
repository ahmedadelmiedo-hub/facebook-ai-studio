import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.script_writer import (
    WriterSettings,
    build_series,
    parse_json_response,
    sanitize_story_id,
    settings_from_args,
    build_parser,
)


class ScriptWriterTests(unittest.TestCase):
    def test_story_id_is_sanitized(self):
        self.assertEqual(sanitize_story_id(" Case 001 / Cairo "), "case-001-cairo")

    def test_parse_json_response_accepts_fenced_object(self):
        self.assertEqual(parse_json_response("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_dry_run_writes_series_assets(self):
        with TemporaryDirectory() as directory:
            settings = WriterSettings(
                api_key="",
                base_url="https://example.invalid/v1",
                model="test-model",
                output_root=Path(directory) / "content",
                dry_run=True,
            )
            plan = build_series(
                settings,
                story_id="case-001",
                requested_theme="",
                language="auto",
            )
            self.assertEqual(plan.episode_count, 4)
            plan_path = settings.output_root / "production" / "case-001" / "series_plan.json"
            self.assertTrue(plan_path.is_file())
            saved_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_plan["episode_count"], 4)
            self.assertTrue((settings.output_root / "scripts" / "long" / "case-001-EP01.txt").is_file())
            self.assertTrue((settings.output_root / "scripts" / "shorts" / "case-001-EP01-HOOK.txt").is_file())
            self.assertTrue((settings.output_root / "scripts" / "shorts" / "case-001-EP01-EXCERPT.txt").is_file())
            self.assertTrue((settings.output_root / "scripts" / "shorts" / "case-001-EP01-CLIFFHANGER.txt").is_file())

    def test_live_mode_requires_provider_key(self):
        parser = build_parser()
        args = parser.parse_args([])
        with self.assertRaises(ValueError):
            settings_from_args(args)


if __name__ == "__main__":
    unittest.main()
