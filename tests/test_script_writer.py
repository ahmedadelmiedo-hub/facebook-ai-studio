import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from core.story_planner import build_series_plan
from core.script_writer import (
    WriterSettings,
    build_series,
    build_short_prompt,
    complete_underlength_episode,
    parse_json_response,
    request_chat,
    retry_after_seconds,
    sanitize_story_id,
    settings_from_args,
    build_parser,
)


class ScriptWriterTests(unittest.TestCase):
    def test_story_id_is_sanitized(self):
        self.assertEqual(sanitize_story_id(" Case 001 / Cairo "), "case-001-cairo")

    def test_parse_json_response_accepts_fenced_object(self):
        self.assertEqual(parse_json_response("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_rate_limit_delay_is_extracted(self):
        self.assertEqual(retry_after_seconds("Please try again in 21.5s."), 23.5)
        self.assertEqual(retry_after_seconds("rate limited"), 25.0)

    def test_groq_request_prioritizes_visible_script_output(self):
        settings = WriterSettings(
            api_key="test-key",
            base_url="https://api.groq.com/openai/v1",
            model="openai/gpt-oss-120b",
            output_root=Path("content"),
            dry_run=False,
        )
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": "نص جاهز"}}]}).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        with patch("core.script_writer.urllib.request.urlopen", return_value=context) as urlopen:
            self.assertEqual(request_chat(settings, [{"role": "user", "content": "اكتب"}], max_tokens=900), "نص جاهز")
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["max_completion_tokens"], 900)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertFalse(payload["include_reasoning"])

    def test_short_prompt_limits_source_excerpt(self):
        plan = build_series_plan(
            story_id="case-001",
            series_title="ملف الاختبار",
            language="الفصحى المعاصرة",
            estimated_total_words=12_000,
        )
        episode = plan.episodes[0]
        prompt = build_short_prompt(
            script="س" * 5_000,
            episode=episode,
            series_title=plan.series_title,
            kind="opening_hook",
            instruction="ابدأ بسؤال مشوق.",
        )
        source = prompt[-1]["content"].split("النص المرجعي من الحلقة (استخدم معناه فقط، ولا تنسخ أكثر من جملة قصيرة):\n", 1)[1].rsplit("\n\nاكتب بين", 1)[0]
        self.assertEqual(len(source), 2_400)

    def test_underlength_episode_is_completed_before_rendering(self):
        plan = build_series_plan(
            story_id="case-001",
            series_title="ملف الاختبار",
            language="الفصحى المعاصرة",
            estimated_total_words=12_000,
        )
        episode = plan.episodes[0]
        settings = WriterSettings(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="test-model",
            output_root=Path("content"),
            dry_run=False,
        )
        with patch("core.script_writer.request_chat", return_value=" ".join(["تكملة"] * 2_500)) as request:
            completed = complete_underlength_episode(
                settings,
                plan=plan,
                episode=episode,
                script="افتتاح قصير",
            )
        self.assertGreaterEqual(len(completed.split()), int(episode.target_words * 0.62))
        request.assert_called_once()

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
