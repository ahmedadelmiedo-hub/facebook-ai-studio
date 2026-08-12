from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from core.automation import run_daily


class AutomationTests(unittest.TestCase):
    def test_dry_run_creates_first_story_and_lists_due_assets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content_root = root / "content"
            content_root.mkdir()
            (content_root / "story_queue.json").write_text(
                json.dumps(
                    {
                        "stories": [
                            {
                                "story_id": "case-001",
                                "theme": "قضية أرشيف غامضة",
                                "language": "auto",
                                "status": "queued",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = run_daily(
                content_root=content_root,
                output_root=root / "storage",
                target_date=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
                dry_run=True,
            )
            self.assertTrue((content_root / "production" / "case-001" / "series_plan.json").is_file())
            self.assertEqual(len(result), 2)
            self.assertEqual({item["content_format"] for item in result}, {"long", "short"})

    def test_initial_launch_selects_first_long_episode_immediately(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content_root = root / "content"
            content_root.mkdir()
            (content_root / "story_queue.json").write_text(
                json.dumps(
                    {"stories": [{
                        "story_id": "case-001",
                        "theme": "قضية أرشيف غامضة",
                        "language": "auto",
                        "status": "queued",
                    }]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            launch_time = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
            result = run_daily(
                content_root=content_root,
                output_root=root / "storage",
                target_date=launch_time,
                dry_run=True,
                publish_first_now=True,
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["asset_id"], "case-001-EP01")
            self.assertEqual(result[0]["content_format"], "long")
            self.assertTrue(result[0]["scheduled_at"].startswith("2026-08-12T12:00:00"))


if __name__ == "__main__":
    unittest.main()
