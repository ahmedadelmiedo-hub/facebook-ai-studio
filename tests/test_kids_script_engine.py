import unittest
from core.kids_script_engine import MockTextProvider, build_prompt, flatten_spoken, validate_script


class KidsScriptEngineTests(unittest.TestCase):
    def setUp(self):
        self.episode = {"episode_id":"kids-ep-001","title":"مصباح نوري لا ينام","learning_goal":"ترتيب الخطوات","conflict":"مصباح لا يهدأ","character_pair":["nouri","rima"],"duration_minutes":3}
        self.rules = {"safety":{"forbidden_topics":["جريمة","رعب"]}}

    def test_mock_provider_is_explicitly_experimental(self):
        result = MockTextProvider().generate("prompt")
        self.assertTrue(result["experimental"])
        self.assertEqual(len(result["scenes"]), 6)

    def test_mock_script_passes_validation(self):
        result = MockTextProvider().generate("prompt")
        validated = validate_script(result, self.episode, self.rules)
        self.assertEqual(validated["duration_minutes"], 3)
        self.assertGreaterEqual(validated["word_count"], 300)

    def test_forbidden_content_fails_validation(self):
        result = MockTextProvider().generate("prompt")
        result["scenes"][0]["dialogue"] = "هذا رعب شديد"
        with self.assertRaises(ValueError):
            validate_script(result, self.episode, self.rules)

    def test_spoken_text_is_deterministic(self):
        result = MockTextProvider().generate("prompt")
        self.assertEqual(flatten_spoken(result), flatten_spoken(result))
        self.assertIn("مصباح", build_prompt(self.episode, {"characters": []}, self.rules))


if __name__ == "__main__":
    unittest.main()
