"""Plan long Arabic crime-story seasons, episodes, engagement breaks, and promotional Shorts.

The planner is deterministic: the AI writer supplies an original story brief and an estimated
story length, then this module selects the episode count, word budgets, and release grid.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from math import ceil
from zoneinfo import ZoneInfo

CAIRO_TZ = ZoneInfo("Africa/Cairo")
NARRATION_WORDS_PER_MINUTE = 130
MIN_EPISODES = 4
MAX_EPISODES = 9
MIN_STORY_WORDS = 12_000
MAX_TARGET_WORDS_PER_EPISODE = 4_200


@dataclass(frozen=True)
class ShortPlan:
    """A promotional short derived from a specific long-form episode."""

    asset_id: str
    kind: str
    scheduled_at: str
    target_seconds: int
    source_instruction: str


@dataclass(frozen=True)
class EpisodePlan:
    """A single long-form chapter and the assets that promote it."""

    id: str
    part_number: int
    title: str
    target_words: int
    target_duration_minutes: int
    long_release_at: str
    engagement_break_after_words: int
    engagement_goal: str
    cliffhanger_goal: str
    shorts: tuple[ShortPlan, ...]


@dataclass(frozen=True)
class SeriesPlan:
    """The production and release plan for one original story."""

    story_id: str
    series_title: str
    language: str
    estimated_total_words: int
    episode_count: int
    release_days: tuple[str, ...]
    timezone: str
    playlist_title: str
    playlist_description: str
    episodes: tuple[EpisodePlan, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def choose_episode_count(estimated_total_words: int) -> int:
    """Select a part count that preserves long-form listening sessions."""
    required_parts = ceil(estimated_total_words / MAX_TARGET_WORDS_PER_EPISODE)
    return max(MIN_EPISODES, min(MAX_EPISODES, required_parts))


def release_days_for(episode_count: int) -> tuple[int, ...]:
    """Use a lighter cadence for short stories and a faster cadence for long arcs."""
    if episode_count <= 5:
        # Monday and Thursday give every episode enough room for discovery Shorts.
        return (0, 3)
    # Sunday, Tuesday, and Thursday keep a long investigation moving without daily uploads.
    return (6, 1, 3)


def release_day_names(weekdays: tuple[int, ...]) -> tuple[str, ...]:
    names = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
    return tuple(names[weekday] for weekday in weekdays)


def next_release_after(after: datetime, weekdays: tuple[int, ...]) -> datetime:
    """Return the next 21:00 Cairo release slot strictly after ``after``."""
    local_after = after.astimezone(CAIRO_TZ)
    for day_offset in range(0, 8):
        candidate_date = (local_after + timedelta(days=day_offset)).date()
        candidate = datetime.combine(candidate_date, time(21, 0), CAIRO_TZ)
        if candidate.weekday() in weekdays and candidate > local_after:
            return candidate
    raise RuntimeError("could not find a release slot")


def split_word_budgets(total_words: int, episode_count: int) -> tuple[int, ...]:
    """Distribute words while giving the opening and ending room to establish and resolve arcs."""
    base = total_words // episode_count
    remainder = total_words % episode_count
    budgets = [base + (1 if index < remainder else 0) for index in range(episode_count)]
    if episode_count >= 4:
        # Move a small amount of text into parts one and the finale for a strong hook and payoff.
        transfer = max(0, min(150, budgets[1] // 20))
        budgets[1] -= transfer
        budgets[0] += transfer // 2
        budgets[-1] += transfer - (transfer // 2)
    return tuple(budgets)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _make_shorts(episode_id: str, release_at: datetime, target_words: int) -> tuple[ShortPlan, ...]:
    """Plan three non-duplicative Shorts that lead viewers back to the full episode."""
    midpoint_start = int(target_words * 0.42)
    ending_start = int(target_words * 0.86)
    return (
        ShortPlan(
            asset_id=f"{episode_id}-HOOK",
            kind="opening_hook",
            scheduled_at=_iso(release_at - timedelta(hours=6)),
            target_seconds=45,
            source_instruction=(
                "اكتب Hook مستقلًا من افتتاحية البارت، يكشف الخطر أو السؤال المركزي "
                "من دون حرق الحل، وينتهي بدعوة لسماع البارت كاملًا من الـPlaylist."
            ),
        ),
        ShortPlan(
            asset_id=f"{episode_id}-EXCERPT",
            kind="midpoint_excerpt",
            scheduled_at=_iso(release_at + timedelta(hours=20)),
            target_seconds=55,
            source_instruction=(
                f"استخرج مقطعًا مشوقًا من قرب الكلمة {midpoint_start}، لا يزيد عن 55 ثانية، "
                "وينتهي بسؤال يدعو المشاهد لكتابة نظريته ثم سماع الحلقة كاملة."
            ),
        ),
        ShortPlan(
            asset_id=f"{episode_id}-CLIFFHANGER",
            kind="cliffhanger",
            scheduled_at=_iso(release_at + timedelta(hours=44)),
            target_seconds=40,
            source_instruction=(
                f"استخرج مشهدًا آمنًا من قرب الكلمة {ending_start} قبل الانعطافة الأخيرة، "
                "ولا تكشف المفاجأة أو هوية الجاني، واختتم بدعوة لمتابعة البارت التالي من الـPlaylist."
            ),
        ),
    )


def build_series_plan(
    *,
    story_id: str,
    series_title: str,
    language: str,
    estimated_total_words: int,
    start_after: datetime | None = None,
) -> SeriesPlan:
    """Build a release-ready plan based on the story's planned narrative size."""
    if not story_id.strip():
        raise ValueError("story_id cannot be empty")
    if not series_title.strip():
        raise ValueError("series_title cannot be empty")
    if estimated_total_words < MIN_STORY_WORDS:
        raise ValueError(
            f"estimated_total_words must be at least {MIN_STORY_WORDS} for a long story"
        )

    episode_count = choose_episode_count(estimated_total_words)
    weekdays = release_days_for(episode_count)
    budgets = split_word_budgets(estimated_total_words, episode_count)
    cursor = start_after or datetime.now(UTC)
    episodes: list[EpisodePlan] = []

    for index, target_words in enumerate(budgets, start=1):
        release_at = next_release_after(cursor, weekdays)
        episode_id = f"{story_id}-EP{index:02d}"
        duration = ceil(target_words / NARRATION_WORDS_PER_MINUTE)
        engagement_after = max(700, int(target_words * 0.52))
        episodes.append(
            EpisodePlan(
                id=episode_id,
                part_number=index,
                title=f"{series_title} | البارت {index} | رواية عربية مسموعة",
                target_words=target_words,
                target_duration_minutes=duration,
                long_release_at=_iso(release_at),
                engagement_break_after_words=engagement_after,
                engagement_goal=(
                    "ادعُ المشاهد بلغة طبيعية لكتابة نظريته حول الدليل أو المشتبه به، "
                    "ثم اطلب الإعجاب والاشتراك لمتابعة كشف الحقيقة."
                ),
                cliffhanger_goal=(
                    "اختم بمعلومة تقلب مسار التحقيق أو تهدد بطل القصة، من دون كشف الحل النهائي."
                ),
                shorts=_make_shorts(episode_id, release_at, target_words),
            )
        )
        cursor = release_at + timedelta(minutes=1)

    return SeriesPlan(
        story_id=story_id.strip(),
        series_title=series_title.strip(),
        language=language.strip() or "auto",
        estimated_total_words=estimated_total_words,
        episode_count=episode_count,
        release_days=release_day_names(weekdays),
        timezone="Africa/Cairo",
        playlist_title=f"{series_title.strip()} | رواية كاملة",
        playlist_description=(
            f"استمع إلى رواية «{series_title.strip()}» كاملة مرتبة بالبارتات. "
            "فعّل الاشتراك ليصلك كل كشف جديد في القضية."
        ),
        episodes=tuple(episodes),
    )
