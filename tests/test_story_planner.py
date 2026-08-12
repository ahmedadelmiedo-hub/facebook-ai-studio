from datetime import UTC, datetime
import unittest

from core.story_planner import (
    build_series_plan,
    choose_episode_count,
    next_release_after,
    release_days_for,
)


class StoryPlannerTests(unittest.TestCase):
    def test_long_story_part_count_scales_with_size(self):
        self.assertEqual(choose_episode_count(16_000), 4)
        self.assertEqual(choose_episode_count(20_000), 5)
        self.assertEqual(choose_episode_count(34_000), 9)

    def test_shorter_long_story_uses_two_weekly_releases(self):
        self.assertEqual(release_days_for(4), (0, 3))
        self.assertEqual(release_days_for(5), (0, 3))

    def test_next_slot_is_cairo_evening(self):
        after = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
        slot = next_release_after(after, (0, 3))
        self.assertEqual(slot.hour, 21)
        self.assertEqual(str(slot.tzinfo), "Africa/Cairo")
        self.assertIn(slot.weekday(), (0, 3))

    def test_plan_includes_playlist_engagement_and_three_shorts_each(self):
        plan = build_series_plan(
            story_id="case-001",
            series_title="ملف الرصد 17",
            language="العامية المصرية المبسطة",
            estimated_total_words=16_000,
            start_after=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(plan.episode_count, 4)
        self.assertEqual(plan.playlist_title, "ملف الرصد 17 | رواية كاملة")
        self.assertEqual(len(plan.episodes), 4)
        self.assertEqual(len(plan.episodes[0].shorts), 3)
        self.assertGreater(plan.episodes[0].engagement_break_after_words, 0)
        self.assertTrue(plan.episodes[0].shorts[0].asset_id.endswith("-HOOK"))

    def test_rejects_non_long_story(self):
        with self.assertRaises(ValueError):
            build_series_plan(
                story_id="short",
                series_title="قصة قصيرة",
                language="الفصحى",
                estimated_total_words=9_000,
            )


if __name__ == "__main__":
    unittest.main()
