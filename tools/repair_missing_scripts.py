"""Repair missing generated scripts for one planned asset without rebuilding its release plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.script_writer import (  # noqa: E402
    MAX_EPISODE_COMPLETION_TOKENS,
    MAX_SHORT_COMPLETION_TOKENS,
    MIN_EPISODE_COMPLETION_RATIO,
    WriterSettings,
    build_episode_prompt,
    build_short_prompt,
    complete_underlength_episode,
    request_chat,
    word_count,
    write_text,
)
from core.story_planner import EpisodePlan, SeriesPlan, ShortPlan  # noqa: E402


def load_series_plan(path: Path) -> SeriesPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    episodes: list[EpisodePlan] = []
    for raw_episode in data["episodes"]:
        shorts = tuple(ShortPlan(**raw_short) for raw_short in raw_episode.get("shorts", []))
        episodes.append(
            EpisodePlan(
                id=str(raw_episode["id"]),
                part_number=int(raw_episode["part_number"]),
                title=str(raw_episode["title"]),
                target_words=int(raw_episode["target_words"]),
                target_duration_minutes=int(raw_episode["target_duration_minutes"]),
                long_release_at=str(raw_episode["long_release_at"]),
                engagement_break_after_words=int(raw_episode["engagement_break_after_words"]),
                engagement_goal=str(raw_episode["engagement_goal"]),
                cliffhanger_goal=str(raw_episode["cliffhanger_goal"]),
                shorts=shorts,
            )
        )
    return SeriesPlan(
        story_id=str(data["story_id"]),
        series_title=str(data["series_title"]),
        language=str(data["language"]),
        estimated_total_words=int(data["estimated_total_words"]),
        episode_count=int(data["episode_count"]),
        release_days=tuple(str(value) for value in data["release_days"]),
        timezone=str(data["timezone"]),
        playlist_title=str(data["playlist_title"]),
        playlist_description=str(data["playlist_description"]),
        episodes=tuple(episodes),
    )


def read_story_bible(path: Path, *, plan: SeriesPlan, story_queue_path: Path) -> dict[str, Any]:
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"story bible must be a JSON object: {path}")
        return value

    queue = json.loads(story_queue_path.read_text(encoding="utf-8"))
    stories = queue.get("stories", [])
    item = next((item for item in stories if str(item.get("story_id")) == plan.story_id), {})
    blueprint = {
        "series_title": plan.series_title,
        "language": plan.language,
        "estimated_total_words": plan.estimated_total_words,
        "logline": str(item.get("theme", "قضية تحقيق غامضة متسلسلة")),
        "setting": "مدينة مصرية معاصرة وأرشيف قضية قديمة",
        "protagonist": "محقق سابق يعود إلى قضية أغلقها قبل سنوات",
        "core_mystery": str(item.get("theme", "من زوّر الدليل، ولماذا عاد إلى الظهور الآن؟")),
        "stakes": "إن أخطأ البطل مرة أخرى قد يضيع حق الضحية ويُتهم بريء.",
        "suspects": ["زميل قديم", "شاهد مجهول", "شخص مرتبط بالأرشيف"],
        "evidence_ladder": ["تسجيل صوتي", "دليل متناقض", "سجل أرشيفي", "شاهد غائب", "قرينة خفية"],
        "final_reveal": "حل أصلي يربط الأدلة السابقة دون كشفه قبل النهاية.",
        "tone": "تحقيق هادئ ومريب يتصاعد مع نهاية كل بارت",
        "content_warning": "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return blueprint


def get_script(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def ensure_episode_script(
    *,
    settings: WriterSettings,
    content_root: Path,
    blueprint: dict[str, Any],
    plan: SeriesPlan,
    episode: EpisodePlan,
    previous_tail: str,
) -> str:
    path = content_root / "scripts" / "long" / f"{episode.id}.txt"
    existing = get_script(path)
    if existing:
        return existing

    script = request_chat(
        settings,
        build_episode_prompt(
            blueprint=blueprint,
            plan=plan,
            episode=episode,
            previous_tail=previous_tail,
        ),
        max_tokens=MAX_EPISODE_COMPLETION_TOKENS,
    )
    script = complete_underlength_episode(settings, plan=plan, episode=episode, script=script)
    minimum_words = int(episode.target_words * MIN_EPISODE_COMPLETION_RATIO)
    if word_count(script) < minimum_words:
        raise RuntimeError(
            f"{episode.id} remains underlength after repair: {word_count(script)} < {minimum_words} words"
        )
    write_text(path, script)
    print(json.dumps({"repaired": str(path), "words": word_count(script)}, ensure_ascii=False))
    return script


def ensure_short_script(
    *,
    settings: WriterSettings,
    content_root: Path,
    plan: SeriesPlan,
    episode: EpisodePlan,
    short: ShortPlan,
    script: str,
) -> Path:
    path = content_root / "scripts" / "shorts" / f"{short.asset_id}.txt"
    if get_script(path):
        return path
    short_script = request_chat(
        settings,
        build_short_prompt(
            script=script,
            episode=episode,
            series_title=plan.series_title,
            kind=short.kind,
            instruction=short.source_instruction,
        ),
        max_tokens=MAX_SHORT_COMPLETION_TOKENS,
    )
    write_text(path, short_script)
    print(json.dumps({"repaired": str(path), "words": word_count(short_script)}, ensure_ascii=False))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair missing scripts for one planned Rowat Alwaqe asset.")
    parser.add_argument("--story-id", default=os.getenv("STORY_ID", "case-001"))
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--content-root", type=Path, default=Path(os.getenv("CONTENT_ROOT", "content")))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    content_root = args.content_root
    production_root = content_root / "production" / args.story_id
    plan = load_series_plan(production_root / "series_plan.json")
    blueprint = read_story_bible(
        production_root / "story_bible.json",
        plan=plan,
        story_queue_path=content_root / "story_queue.json",
    )
    settings = WriterSettings(
        api_key=os.getenv("SCRIPTWRITER_API_KEY", "").strip(),
        base_url=os.getenv("SCRIPTWRITER_BASE_URL", "https://api.openai.com/v1").strip(),
        model=os.getenv("SCRIPTWRITER_MODEL", "gpt-5").strip(),
        output_root=content_root,
        dry_run=False,
    )
    if not settings.api_key:
        raise ValueError("SCRIPTWRITER_API_KEY is not configured")

    episode_by_id = {episode.id: episode for episode in plan.episodes}
    target_episode_id = args.asset_id.rsplit("-", 1)[0] if args.asset_id.endswith(("-HOOK", "-EXCERPT", "-CLIFFHANGER")) else args.asset_id
    if target_episode_id not in episode_by_id:
        raise ValueError(f"asset does not belong to the current plan: {args.asset_id}")

    previous_tail = ""
    target_episode = episode_by_id[target_episode_id]
    for episode in plan.episodes:
        episode_path = content_root / "scripts" / "long" / f"{episode.id}.txt"
        episode_script = get_script(episode_path)
        if episode.id == target_episode_id:
            episode_script = ensure_episode_script(
                settings=settings,
                content_root=content_root,
                blueprint=blueprint,
                plan=plan,
                episode=episode,
                previous_tail=previous_tail,
            )
        if episode_script:
            previous_tail = episode_script[-2_500:]
        if episode.id != target_episode_id:
            continue
        short_by_id = {short.asset_id: short for short in episode.shorts}
        short = short_by_id.get(args.asset_id)
        if short is None:
            raise ValueError(f"asset is not a planned Short: {args.asset_id}")
        ensure_short_script(
            settings=settings,
            content_root=content_root,
            plan=plan,
            episode=target_episode,
            short=short,
            script=episode_script,
        )
        return 0

    raise RuntimeError(f"episode not found: {target_episode_id}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
