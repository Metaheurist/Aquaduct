from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalityPreset:
    id: str
    label: str
    description: str
    style_rules: list[str]
    do_dont: list[str]


def get_personality_presets() -> list[PersonalityPreset]:
    return [
        PersonalityPreset(
            id="neutral",
            label="Neutral / Newsroom",
            description="Straight, factual, low-flair delivery.",
            style_rules=[
                "Concise, factual, no hype words.",
                "Explain what it is, who it's for, and one key limitation.",
            ],
            do_dont=[
                "Do: sound credible and calm.",
                "Don't: use slang or excessive emojis/punctuation.",
            ],
        ),
        PersonalityPreset(
            id="hype",
            label="Hype / Creator",
            description="High energy, punchy creator voice with momentum.",
            style_rules=[
                "Short sentences, fast pacing, strong hook.",
                "Use one-liners and power words, but keep facts accurate.",
            ],
            do_dont=[
                "Do: use excitement and curiosity.",
                "Don't: overpromise or claim guarantees.",
            ],
        ),
        PersonalityPreset(
            id="analytical",
            label="Analytical / Engineer",
            description="Practical, structured, detail-oriented tech breakdown.",
            style_rules=[
                "Use clear structure: problem → solution → how it works → trade-offs.",
                "Mention 1–2 concrete use cases and 1 caveat.",
            ],
            do_dont=[
                "Do: be specific and grounded.",
                "Don't: ramble or use vague adjectives.",
            ],
        ),
        PersonalityPreset(
            id="comedic",
            label="Comedic / Punchy",
            description="Light humor, quick punchlines, still informative.",
            style_rules=[
                "Use 1–2 tasteful jokes or metaphors.",
                "Keep the core facts intact and easy to follow.",
            ],
            do_dont=[
                "Do: keep jokes short and optional.",
                "Don't: mock people or dunk on users.",
            ],
        ),
        PersonalityPreset(
            id="skeptical",
            label="Skeptical / Myth-buster",
            description="Cautious, checks claims, highlights limitations.",
            style_rules=[
                "Lead with: what's real vs what's marketing.",
                "Call out risks: privacy, accuracy, cost, lock-in.",
            ],
            do_dont=[
                "Do: be fair and balanced.",
                "Don't: be cynical without evidence.",
            ],
        ),
        PersonalityPreset(
            id="cozy",
            label="Cozy / Friendly explainer",
            description="Warm, approachable, like explaining to a friend.",
            style_rules=[
                "Simple language, reassuring tone.",
                "Give a gentle 'try this first' recommendation.",
            ],
            do_dont=[
                "Do: be supportive and clear.",
                "Don't: sound salesy.",
            ],
        ),
        PersonalityPreset(
            id="urgent",
            label="Urgent / Breaking news",
            description="Breaking-news vibe, crisp and time-sensitive.",
            style_rules=[
                "Start with a 'breaking' style hook.",
                "Focus on the newness and immediate impact.",
            ],
            do_dont=[
                "Do: keep it fast and direct.",
                "Don't: exaggerate urgency if not warranted.",
            ],
        ),
        PersonalityPreset(
            id="contrarian",
            label="Contrarian / Hot take",
            description="Opinionated angle with a strong but fair thesis.",
            style_rules=[
                "Open with a counterintuitive claim, then justify it.",
                "Include 1 pro and 1 con to stay credible.",
            ],
            do_dont=[
                "Do: be bold but evidence-based.",
                "Don't: be inflammatory or disrespectful.",
            ],
        ),
    ]


def get_personality_by_id(pid: str) -> PersonalityPreset:
    pid = (pid or "").strip().lower() or "neutral"
    for p in get_personality_presets():
        if p.id == pid:
            return p
    return get_personality_presets()[0]

