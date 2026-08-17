import unittest

from core.performance_planner import split_script_into_performance_segments


class PerformancePlannerTests(unittest.TestCase):
    def test_split_is_sentence_aware_and_stable(self):
        text = "الجملة الأولى تحمل وصفًا طويلًا لممر مظلم داخل المبنى. الجملة الثانية تكشف سرًا جديدًا خلف الباب الحديدي. الجملة الثالثة تفتح الطريق إلى غرفة الأرشيف القديمة."
        segments = split_script_into_performance_segments(text, max_characters=120)
        self.assertEqual([segment.segment_id for segment in segments], ["A001", "A002"])
        self.assertEqual(" ".join(segment.text for segment in segments), text)
        self.assertEqual(segments[0].emotion, "serious")
        self.assertEqual(segments[1].emotion, "quiet_suspense")

    def test_long_sentence_is_split_without_losing_words(self):
        text = "كلمة " * 100
        segments = split_script_into_performance_segments(text, max_characters=120)
        self.assertGreater(len(segments), 1)
        self.assertEqual(" ".join(segment.text for segment in segments), text.strip())

    def test_empty_script_rejected(self):
        with self.assertRaises(ValueError):
            split_script_into_performance_segments("   ")


if __name__ == "__main__":
    unittest.main()
