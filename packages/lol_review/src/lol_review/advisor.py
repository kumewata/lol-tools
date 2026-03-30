"""Rule-based game analysis to detect improvement areas."""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from lol_review.models import AnalysisResult


@dataclass
class Finding:
    category: str  # cs, deaths, vision, build, kda, winrate
    severity: str  # critical, warning, info
    message: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


# Thresholds (role-based CS targets)
CS_THRESHOLDS: dict[str, tuple[float, float]] = {
    # (very_low, low)
    "JUNGLE": (3.0, 4.5),
    "UTILITY": (0.5, 1.5),
    "TOP": (5.0, 6.5),
    "MIDDLE": (5.0, 6.5),
    "BOTTOM": (5.5, 7.0),
}
CS_PER_MIN_LOW = 5.0  # fallback
CS_PER_MIN_VERY_LOW = 3.5  # fallback
VISION_SCORE_PER_MIN_LOW = 0.5
EARLY_GAME_SECONDS = 600  # 10 minutes
EARLY_DEATH_RATIO_THRESHOLD = 0.5  # 50%+ deaths before 10min
FIRST_CORE_LATE_SECONDS = 1200  # 20 minutes
KDA_LOW = 2.0
KDA_VERY_LOW = 1.0

# Kill participation thresholds by role
KP_THRESHOLDS: dict[str, float] = {
    "UTILITY": 0.50,
    "JUNGLE": 0.40,
    "MIDDLE": 0.35,
    "TOP": 0.30,
    "BOTTOM": 0.35,
}


def analyze_findings(result: AnalysisResult) -> list[Finding]:
    """Analyze match data and return a list of findings."""
    findings: list[Finding] = []

    if result.total_games == 0:
        return findings

    findings.extend(_check_cs(result))
    findings.extend(_check_kill_participation(result))
    findings.extend(_check_deaths(result))
    findings.extend(_check_vision(result))
    findings.extend(_check_build_timing(result))
    findings.extend(_check_kda(result))
    findings.extend(_check_winrate(result))
    findings.extend(_check_champion_pool(result))

    return findings


def _check_cs(result: AnalysisResult) -> list[Finding]:
    findings = []
    # Group matches by role for role-specific CS evaluation
    role_matches: dict[str, list] = {}
    for m in result.matches:
        role = m.role or "UNKNOWN"
        role_matches.setdefault(role, []).append(m)

    role_labels = {
        "JUNGLE": "ジャングル",
        "UTILITY": "サポート",
        "TOP": "トップ",
        "MIDDLE": "ミッド",
        "BOTTOM": "ボット",
    }

    for role, matches in role_matches.items():
        avg_cs = sum(m.cs_per_min for m in matches) / len(matches)
        very_low, low = CS_THRESHOLDS.get(role, (CS_PER_MIN_VERY_LOW, CS_PER_MIN_LOW))
        label = role_labels.get(role, role)
        target = f"{low:.1f}"

        if avg_cs < very_low:
            findings.append(Finding(
                category="cs",
                severity="critical",
                message=f"CS/min が非常に低い（{label}）",
                detail=f"平均 {avg_cs:.1f} CS/min（{label}目安: {target}以上）",
            ))
        elif avg_cs < low:
            findings.append(Finding(
                category="cs",
                severity="warning",
                message=f"CS/min が低め（{label}）",
                detail=f"平均 {avg_cs:.1f} CS/min（{label}目安: {target}以上）",
            ))
    return findings


def _check_kill_participation(result: AnalysisResult) -> list[Finding]:
    findings = []
    role_matches: dict[str, list] = {}
    for m in result.matches:
        role = m.role or "UNKNOWN"
        role_matches.setdefault(role, []).append(m)

    role_labels = {
        "JUNGLE": "ジャングル", "UTILITY": "サポート",
        "TOP": "トップ", "MIDDLE": "ミッド", "BOTTOM": "ボット",
    }
    for role, matches in role_matches.items():
        avg_kp = sum(m.kill_participation for m in matches) / len(matches)
        threshold = KP_THRESHOLDS.get(role, 0.35)
        label = role_labels.get(role, role)
        if avg_kp < threshold:
            findings.append(Finding(
                category="kill_participation",
                severity="warning",
                message=f"キル参加率が低い（{label}）",
                detail=f"平均 {avg_kp * 100:.0f}%（{label}目安: {threshold * 100:.0f}%以上）",
            ))
    return findings


def _check_deaths(result: AnalysisResult) -> list[Finding]:
    findings = []
    # Check for early game deaths pattern
    early_death_matches = 0
    for ps in result.player_stats:
        if not ps.death_timestamps:
            continue
        early_deaths = sum(1 for t in ps.death_timestamps if t <= EARLY_GAME_SECONDS)
        total_deaths = len(ps.death_timestamps)
        if total_deaths > 0 and early_deaths / total_deaths >= EARLY_DEATH_RATIO_THRESHOLD:
            early_death_matches += 1

    if result.total_games > 0 and early_death_matches / result.total_games >= 0.4:
        findings.append(Finding(
            category="deaths",
            severity="warning",
            message="序盤のデスが多い",
            detail=f"{result.total_games}試合中{early_death_matches}試合で"
                   f"デスの半数以上が10分以内に発生",
        ))

    # Average deaths per game
    total_deaths = sum(m.deaths for m in result.matches)
    avg_deaths = total_deaths / result.total_games
    if avg_deaths >= 7:
        findings.append(Finding(
            category="deaths",
            severity="critical",
            message="平均デス数が非常に多い",
            detail=f"平均 {avg_deaths:.1f} デス/試合",
        ))
    elif avg_deaths >= 5:
        findings.append(Finding(
            category="deaths",
            severity="warning",
            message="平均デス数が多め",
            detail=f"平均 {avg_deaths:.1f} デス/試合",
        ))
    return findings


def _check_vision(result: AnalysisResult) -> list[Finding]:
    findings = []
    total_vision_per_min = []
    for m in result.matches:
        minutes = m.game_duration_seconds / 60
        if minutes > 0:
            total_vision_per_min.append(m.vision_score / minutes)

    if total_vision_per_min:
        avg_vision_per_min = sum(total_vision_per_min) / len(total_vision_per_min)
        if avg_vision_per_min < VISION_SCORE_PER_MIN_LOW:
            findings.append(Finding(
                category="vision",
                severity="warning",
                message="ビジョンスコアが低い",
                detail=f"平均 {avg_vision_per_min:.2f}/min（目安: 0.5以上）",
            ))
    return findings


def _check_build_timing(result: AnalysisResult) -> list[Finding]:
    findings = []
    first_core_times = []
    for ps in result.player_stats:
        for item in ps.item_purchases:
            if item.get("item_type") == "completed":
                first_core_times.append(item["timestamp"])
                break

    if first_core_times:
        avg_first_core = sum(first_core_times) / len(first_core_times)
        if avg_first_core > FIRST_CORE_LATE_SECONDS:
            mins = int(avg_first_core // 60)
            secs = int(avg_first_core % 60)
            findings.append(Finding(
                category="build",
                severity="warning",
                message="コアアイテムの完成が遅い",
                detail=f"1個目のコア完成が平均 {mins}:{secs:02d}（目安: 15分以内）",
            ))
    return findings


def _check_kda(result: AnalysisResult) -> list[Finding]:
    findings = []
    avg_kda = result.avg_kda
    if math.isfinite(avg_kda):
        if avg_kda < KDA_VERY_LOW:
            findings.append(Finding(
                category="kda",
                severity="critical",
                message="KDA が非常に低い",
                detail=f"平均 KDA: {avg_kda:.2f}（目安: 2.0以上）",
            ))
        elif avg_kda < KDA_LOW:
            findings.append(Finding(
                category="kda",
                severity="warning",
                message="KDA が低め",
                detail=f"平均 KDA: {avg_kda:.2f}（目安: 3.0以上）",
            ))
    return findings


def _check_winrate(result: AnalysisResult) -> list[Finding]:
    findings = []
    if result.total_games >= 5 and result.win_rate < 0.4:
        findings.append(Finding(
            category="winrate",
            severity="warning",
            message="勝率が低い",
            detail=f"{result.win_rate * 100:.0f}%（{result.wins}勝{result.losses}敗）",
        ))
    return findings


def _check_champion_pool(result: AnalysisResult) -> list[Finding]:
    findings = []
    # Champions with low winrate but many games
    for cs in result.champion_stats:
        if cs.games >= 3 and cs.win_rate < 0.3:
            findings.append(Finding(
                category="champion",
                severity="info",
                message=f"{cs.champion} の勝率が低い",
                detail=f"{cs.games}試合で勝率 {cs.win_rate * 100:.0f}%",
            ))
    return findings
