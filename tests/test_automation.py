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


if __name__ == "__main__":
    unittest.main()
