"""
Smart Study Planner AI - Knowledge Base (Phase 3)
Contains explicit IF-THEN rules for the rule-based expert system.

Each rule has:
  - id          : Unique rule identifier (e.g. "R01")
  - name        : Human-readable rule name
  - priority    : Evaluation order (lower number fires first)
  - conditions  : callable(facts: dict) -> bool
  - action      : dict with 'priority', 'session_type', 'adjustment_factor'
  - explanation : Template string for the explanation generator
"""

from typing import Callable, Dict, Any, List


# ---------------------------------------------------------------------------
# Rule dataclass-style structure (plain dict for Python 3.6+ compatibility)
# ---------------------------------------------------------------------------

def _rule(rule_id: str, name: str, priority: int,
          conditions: Callable[[Dict], bool],
          action: Dict[str, Any],
          explanation: str) -> Dict:
    return {
        "id": rule_id,
        "name": name,
        "priority": priority,
        "conditions": conditions,
        "action": action,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Helper lambdas used by conditions (keep pure – no side effects)
# ---------------------------------------------------------------------------

def _days_remaining(facts: Dict) -> int:
    """Return days_remaining from facts, defaulting to a large number if absent."""
    return facts.get("days_remaining", 9999)


def _completion_pct(facts: Dict) -> float:
    total = facts.get("syllabus_units_total", 1)
    done = facts.get("units_completed", 0)
    return (done / total * 100) if total > 0 else 100.0


def _difficulty(facts: Dict) -> str:
    return facts.get("difficulty_level", "medium").lower()


def _fatigue(facts: Dict) -> str:
    return facts.get("fatigue_level", "medium").lower()


# ---------------------------------------------------------------------------
# THE KNOWLEDGE BASE  –  ordered list of rules
# Rules are evaluated top-to-bottom; first match wins (unless noted)
# ---------------------------------------------------------------------------

RULES: List[Dict] = [

    # ── CRITICAL: Overdue exam ──────────────────────────────────────────────
    _rule(
        rule_id="R01",
        name="Emergency Cram – Overdue Exam",
        priority=1,
        conditions=lambda f: _days_remaining(f) < 0,
        action={
            "subject_priority": "CRITICAL",
            "session_type": "emergency_cram",
            "adjustment_factor": 1.0,
            "label": "OVERDUE – skip if possible",
        },
        explanation=(
            "Rule R01 fired: Exam date has already passed (days_remaining={days_remaining}). "
            "This subject is marked CRITICAL/overdue. Focus on any remaining assessments or use "
            "time for other subjects."
        ),
    ),

    # ── CRITICAL: Exam in ≤2 days, not finished ─────────────────────────────
    _rule(
        rule_id="R02",
        name="Emergency Cram – Exam in ≤2 Days",
        priority=2,
        conditions=lambda f: 0 <= _days_remaining(f) <= 2 and _completion_pct(f) < 100,
        action={
            "subject_priority": "CRITICAL",
            "session_type": "emergency_cram",
            "adjustment_factor": 1.0,
            "label": "Emergency cram – exam imminent",
        },
        explanation=(
            "Rule R02 fired: Only {days_remaining} day(s) until the {subject_name} exam and "
            "syllabus is {completion_pct:.0f}% complete. Immediately allocate maximum study time "
            "using short, intensive sessions."
        ),
    ),

    # ── HIGH: Hard subject, exam soon (3-5 days), incomplete ────────────────
    _rule(
        rule_id="R03",
        name="High Priority – Hard Subject, Exam Soon",
        priority=3,
        conditions=lambda f: (
            3 <= _days_remaining(f) <= 5
            and _difficulty(f) == "hard"
            and _completion_pct(f) < 80
        ),
        action={
            "subject_priority": "HIGH",
            "session_type": "new_concept",
            "adjustment_factor": 0.9,
            "label": "Hard subject, exam approaching",
        },
        explanation=(
            "Rule R03 fired: {subject_name} is a HARD subject with only {days_remaining} days "
            "until the exam and {completion_pct:.0f}% of the syllabus done. High-priority "
            "sessions are needed to cover remaining units."
        ),
    ),

    # ── HIGH: Any difficulty, exam in 3-7 days, < 50% done ─────────────────
    _rule(
        rule_id="R04",
        name="High Priority – Low Completion, Exam Within a Week",
        priority=4,
        conditions=lambda f: (
            3 <= _days_remaining(f) <= 7
            and _completion_pct(f) < 50
        ),
        action={
            "subject_priority": "HIGH",
            "session_type": "new_concept",
            "adjustment_factor": 0.85,
            "label": "< 50% done, exam within a week",
        },
        explanation=(
            "Rule R04 fired: Only {completion_pct:.0f}% of {subject_name} completed with "
            "{days_remaining} days left. Exam is close and a large portion remains – prioritise "
            "this subject immediately."
        ),
    ),

    # ── HIGH: Fatigue high, exam ≤5 days – shorten sessions ────────────────
    _rule(
        rule_id="R05",
        name="High Priority – High Fatigue, Exam ≤5 Days",
        priority=5,
        conditions=lambda f: (
            _days_remaining(f) <= 5
            and _fatigue(f) == "high"
            and _completion_pct(f) < 100
        ),
        action={
            "subject_priority": "HIGH",
            "session_type": "revision",
            "adjustment_factor": 0.6,
            "label": "High fatigue – reduced session length",
        },
        explanation=(
            "Rule R05 fired: Student fatigue is HIGH with only {days_remaining} days to the "
            "{subject_name} exam. Shorter revision sessions (60% of normal duration) are "
            "recommended to prevent burnout."
        ),
    ),

    # ── MEDIUM: Exam 6-14 days, medium/hard, < 70% done ────────────────────
    _rule(
        rule_id="R06",
        name="Medium Priority – Approaching Exam, Moderate Progress",
        priority=6,
        conditions=lambda f: (
            6 <= _days_remaining(f) <= 14
            and _difficulty(f) in ("medium", "hard")
            and _completion_pct(f) < 70
        ),
        action={
            "subject_priority": "MEDIUM",
            "session_type": "new_concept",
            "adjustment_factor": 0.75,
            "label": "Approaching exam, steady progress needed",
        },
        explanation=(
            "Rule R06 fired: {subject_name} has {days_remaining} days until the exam with "
            "{completion_pct:.0f}% completed. Medium-priority sessions will keep progress on track."
        ),
    ),

    # ── MEDIUM: Exam 6-14 days, easy, < 60% done ────────────────────────────
    _rule(
        rule_id="R07",
        name="Medium Priority – Easy Subject, Approaching Exam",
        priority=7,
        conditions=lambda f: (
            6 <= _days_remaining(f) <= 14
            and _difficulty(f) == "easy"
            and _completion_pct(f) < 60
        ),
        action={
            "subject_priority": "MEDIUM",
            "session_type": "new_concept",
            "adjustment_factor": 0.65,
            "label": "Easy subject, moderate urgency",
        },
        explanation=(
            "Rule R07 fired: {subject_name} is an EASY subject but only {completion_pct:.0f}% "
            "done with {days_remaining} days left. Allocate moderate study time to finish comfortably."
        ),
    ),

    # ── MEDIUM: High fatigue, exam 6-14 days ────────────────────────────────
    _rule(
        rule_id="R08",
        name="Fatigue Reduction – Medium Priority Revision",
        priority=8,
        conditions=lambda f: (
            6 <= _days_remaining(f) <= 14
            and _fatigue(f) == "high"
            and _completion_pct(f) < 100
        ),
        action={
            "subject_priority": "MEDIUM",
            "session_type": "revision",
            "adjustment_factor": 0.5,
            "label": "High fatigue – light revision only",
        },
        explanation=(
            "Rule R08 fired: Student is highly fatigued with {days_remaining} days to the "
            "{subject_name} exam. Use light, spaced-out revision sessions (50% normal length) "
            "to retain information without exhaustion."
        ),
    ),

    # ── LOW: Nearly complete (≥90%), exam > 7 days ──────────────────────────
    _rule(
        rule_id="R09",
        name="Low Priority – Nearly Complete Subject",
        priority=9,
        conditions=lambda f: (
            _completion_pct(f) >= 90
            and _days_remaining(f) > 7
        ),
        action={
            "subject_priority": "LOW",
            "session_type": "revision",
            "adjustment_factor": 0.4,
            "label": "Almost done – light revision only",
        },
        explanation=(
            "Rule R09 fired: {subject_name} is {completion_pct:.0f}% complete with "
            "{days_remaining} days remaining. Only brief revision is needed – allocate minimal "
            "time and focus energy on higher-priority subjects."
        ),
    ),

    # ── LOW: Exam far away (> 14 days), easy subject ────────────────────────
    _rule(
        rule_id="R10",
        name="Low Priority – Distant Exam, Easy Subject",
        priority=10,
        conditions=lambda f: (
            _days_remaining(f) > 14
            and _difficulty(f) == "easy"
        ),
        action={
            "subject_priority": "LOW",
            "session_type": "new_concept",
            "adjustment_factor": 0.3,
            "label": "Easy subject, exam is far",
        },
        explanation=(
            "Rule R10 fired: {subject_name} is an EASY subject with {days_remaining} days until "
            "the exam. Low urgency – schedule a short study session to maintain momentum."
        ),
    ),

    # ── LOW: Exam far (>14 days), medium difficulty ──────────────────────────
    _rule(
        rule_id="R11",
        name="Low Priority – Distant Exam, Medium Subject",
        priority=11,
        conditions=lambda f: (
            _days_remaining(f) > 14
            and _difficulty(f) == "medium"
        ),
        action={
            "subject_priority": "MEDIUM",
            "session_type": "new_concept",
            "adjustment_factor": 0.5,
            "label": "Medium subject, exam distant",
        },
        explanation=(
            "Rule R11 fired: {subject_name} has a distant exam ({days_remaining} days). "
            "Medium difficulty means regular, moderate study sessions will build a solid base."
        ),
    ),

    # ── MEDIUM: Practice problems – hard subject, > 60% done ────────────────
    _rule(
        rule_id="R12",
        name="Practice Priority – Hard Subject, Good Progress",
        priority=12,
        conditions=lambda f: (
            _difficulty(f) == "hard"
            and _completion_pct(f) >= 60
            and _days_remaining(f) > 5
        ),
        action={
            "subject_priority": "MEDIUM",
            "session_type": "practice_problems",
            "adjustment_factor": 0.7,
            "label": "Hard subject, needs practice problems",
        },
        explanation=(
            "Rule R12 fired: {subject_name} is HARD and {completion_pct:.0f}% complete. "
            "With {days_remaining} days left, switch from learning new content to solving "
            "practice problems for deeper understanding."
        ),
    ),

    # ── LOW: Completely done subject ─────────────────────────────────────────
    _rule(
        rule_id="R13",
        name="Skip – Syllabus 100% Complete",
        priority=13,
        conditions=lambda f: _completion_pct(f) >= 100,
        action={
            "subject_priority": "LOW",
            "session_type": "revision",
            "adjustment_factor": 0.2,
            "label": "Syllabus complete – quick revision only",
        },
        explanation=(
            "Rule R13 fired: {subject_name} syllabus is 100% complete. A very short revision "
            "session is scheduled to reinforce memory. No new content needed."
        ),
    ),

    # ── MEDIUM fallback – default when no other rule matches ─────────────────
    _rule(
        rule_id="R14",
        name="Default – Steady Study",
        priority=14,
        conditions=lambda f: True,          # always matches (catch-all)
        action={
            "subject_priority": "MEDIUM",
            "session_type": "new_concept",
            "adjustment_factor": 0.6,
            "label": "Default steady-study session",
        },
        explanation=(
            "Rule R14 fired (default): No specific urgency rule applies to {subject_name}. "
            "A standard study session is scheduled based on the available time budget."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_rules() -> List[Dict]:
    """Return all rules sorted by priority (ascending)."""
    return sorted(RULES, key=lambda r: r["priority"])


def get_rule_by_id(rule_id: str) -> Dict | None:
    """Retrieve a single rule by its ID string."""
    for rule in RULES:
        if rule["id"] == rule_id:
            return rule
    return None
