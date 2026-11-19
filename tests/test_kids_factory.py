import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.kids_factory import fingerprint, safety_issues, validate_story


class KidsFactoryTests(unittest.TestCase):
    def setUp(self):
        self.rules = {
            "safety": {"forbidden_topics": ["جريمة", "رعب"]},
            "originality": {"fingerprint_fields": ["content_type", "learning_goal", "setting", "conflict", "character_pair"]},
        }
        self.story = {
            "episode_id": "kids-ep-001", "title": "مصباح نوري لا ينام",
            "content_type": "educational_story", "learning_goal": "ترتيب الخطوات",
            "setting": "غرفة نوم", "conflict": "مصباح لا يهدأ",
            "character_pair": ["nouri", "rima"], "duration_minutes": 3,
        }

    def test_safe_story_has_no_policy_issues(self):
        self.assertEqual(validate_story(self.story, {**self.rules, "audience": {}}), [])

    def test_forbidden_topic_is_rejected(self):
        story = {**self.story, "conflict": "رعب في الغرفة"}
        self.assertTrue(safety_issues(story, self.rules))

    def test_fingerprint_is_stable_and_changes_with_core_idea(self):
        first = fingerprint(self.story, self.rules)
        self.assertEqual(first, fingerprint(dict(self.story), self.rules))
        self.assertNotEqual(first, fingerprint({**self.story, "learning_goal": "تمييز الألوان"}, self.rules))

    def test_three_minute_target_is_enforced(self):
        self.assertTrue(validate_story({**self.story, "duration_minutes": 4}, {**self.rules, "audience": {}}))


if __name__ == "__main__":
    unittest.main()
