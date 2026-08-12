from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.content_pipeline import (
    due_assets_for_date,
    load_series_assets,
    load_state,
    mark_uploaded,
    save_state,
)
from core.story_planner import build_series_plan


class ContentPipelineTests(unittest.TestCase):
    def _make_plan(self, root: Path) -> None:
        plan = build_series_plan(
            story_id="case-001",
            series_title="ملف الرصد 17",
            language="العامية المصرية المبسطة",
            estimated_total_words=16_000,
            start_after=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        )
        folder = root / "production" / "case-001"
        folder.mkdir(parents=True)
        (folder / "series_plan.json").write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False), encoding="utf-8"
        )

    def test_loads_one_long_and_three_shorts_per_part(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "content"
            self._make_plan(root)
            assets = load_series_assets(root, "case-001")
            self.assertEqual(len(assets), 16)
            self.assertEqual(len([asset for asset in assets if asset.content_format == "long"]), 4)
            self.assertEqual(len([asset for asset in assets if asset.content_format == "short"]), 12)

    def test_due_assets_are_not_repeated_after_upload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "content"
            self._make_plan(root)
            assets = load_series_assets(root, "case-001")
            state = load_state(root, "case-001")
            release_day = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
            due = due_assets_for_date(assets, state, release_day)
            self.assertEqual(len(due), 2)
            self.assertEqual({asset.content_format for asset in due}, {"long", "short"})
            mark_uploaded(state, due[0], video_id="abc", playlist_id="playlist")
            self.assertEqual(len(due_assets_for_date(assets, state, release_day)), 1)
            self.assertTrue(save_state(root, "case-001", state).is_file())


if __name__ == "__main__":
    unittest.main()
