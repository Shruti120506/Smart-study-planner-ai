"""
Smart Study Planner AI – Working Memory (Phase 3)

Working Memory holds the current state of facts that the inference engine
operates on.  Facts are derived from the SQLite database and represent
everything the AI "knows" at planning time:

  - Subject details (name, difficulty, exam_date, syllabus progress)
  - Computed facts (days_remaining, completion_pct, remaining_units)
  - Student preferences (available hours, fatigue level, focus span)
  - Planning metadata (plan_date, budget remaining)

The WorkingMemory class is intentionally kept as a pure data container;
it does NOT perform inference itself.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional


class SubjectFacts:
    """
    A set of facts about a single subject, computed from the DB row and
    the student's study preferences.
    """

    def __init__(self, subject_row: Dict, preferences: Dict,
                 reference_date: Optional[date] = None):
        today = reference_date or date.today()

        # ── Direct DB fields ────────────────────────────────────────────────
        self.subject_id: int = subject_row.get("id", 0)
        self.subject_name: str = subject_row.get("name", "Unknown")
        self.difficulty_level: str = subject_row.get("difficulty_level", "medium").lower()
        self.target_grade: str = subject_row.get("target_grade", "A")
        self.syllabus_units_total: int = int(subject_row.get("syllabus_units_total", 5))
        self.units_completed: int = int(subject_row.get("units_completed", 0))

        # ── Exam date and days remaining ────────────────────────────────────
        exam_date_str = subject_row.get("exam_date")
        if exam_date_str:
            try:
                self.exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
                self.days_remaining = (self.exam_date - today).days
            except ValueError:
                self.exam_date = None
                self.days_remaining = 9999
        else:
            self.exam_date = None
            self.days_remaining = 9999

        # ── Derived facts ───────────────────────────────────────────────────
        total = self.syllabus_units_total or 1
        self.completion_pct: float = round(
            (self.units_completed / total) * 100, 1
        )
        self.remaining_units: int = max(0, self.syllabus_units_total - self.units_completed)

        # ── Student preferences (shared, carried over per subject) ──────────
        self.daily_available_hours: float = float(preferences.get("daily_available_hours", 4.0))
        self.fatigue_level: str = preferences.get("fatigue_level", "medium").lower()
        self.focus_span_minutes: int = int(preferences.get("focus_span_minutes", 45))
        self.preferred_time_of_day: str = preferences.get("preferred_time_of_day", "morning").lower()

    def to_dict(self) -> Dict[str, Any]:
        """Serialise all facts to a plain dict (used by rule conditions)."""
        return {
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "difficulty_level": self.difficulty_level,
            "target_grade": self.target_grade,
            "syllabus_units_total": self.syllabus_units_total,
            "units_completed": self.units_completed,
            "exam_date": self.exam_date.isoformat() if self.exam_date else None,
            "days_remaining": self.days_remaining,
            "completion_pct": self.completion_pct,
            "remaining_units": self.remaining_units,
            "daily_available_hours": self.daily_available_hours,
            "fatigue_level": self.fatigue_level,
            "focus_span_minutes": self.focus_span_minutes,
            "preferred_time_of_day": self.preferred_time_of_day,
        }


class WorkingMemory:
    """
    Central working-memory store for a single planning session.

    Holds:
      - all SubjectFacts objects
      - student preferences
      - the daily time budget (minutes remaining after each rule fires)
      - the list of fired rule IDs (prevents the same rule firing twice
        on the same subject in one planning cycle)
    """

    def __init__(self, subjects: List[Dict], preferences: Dict,
                 reference_date: Optional[date] = None):
        self.reference_date: date = reference_date or date.today()
        self.preferences: Dict = preferences

        # Build SubjectFacts for each subject
        self.subject_facts: List[SubjectFacts] = [
            SubjectFacts(s, preferences, self.reference_date)
            for s in subjects
        ]

        # Daily time budget in minutes
        daily_hours = float(preferences.get("daily_available_hours", 4.0))
        self.total_budget_minutes: float = daily_hours * 60.0
        self.remaining_budget_minutes: float = self.total_budget_minutes

        # Fired rule tracking: {subject_id: [rule_id, ...]}
        self._fired_rules: Dict[int, List[str]] = {}

        # Accumulated plan items (populated by forward chainer)
        self.plan_items: List[Dict] = []

        # Backward chaining goal results
        self.backward_results: List[Dict] = []

    # ── Budget helpers ──────────────────────────────────────────────────────

    def allocate_minutes(self, minutes: float) -> float:
        """
        Consume `minutes` from the daily budget.
        Returns the actual minutes allocated (capped by remaining budget).
        """
        actual = min(minutes, self.remaining_budget_minutes)
        self.remaining_budget_minutes -= actual
        return actual

    def has_budget(self, minimum_minutes: float = 10.0) -> bool:
        """Returns True if at least `minimum_minutes` of budget remain."""
        return self.remaining_budget_minutes >= minimum_minutes

    # ── Rule-firing helpers ─────────────────────────────────────────────────

    def already_fired(self, subject_id: int, rule_id: str) -> bool:
        return rule_id in self._fired_rules.get(subject_id, [])

    def mark_fired(self, subject_id: int, rule_id: str) -> None:
        self._fired_rules.setdefault(subject_id, []).append(rule_id)

    # ── Accessors ───────────────────────────────────────────────────────────

    def get_fired_rules(self) -> Dict[int, List[str]]:
        return dict(self._fired_rules)

    def add_plan_item(self, item: Dict) -> None:
        self.plan_items.append(item)

    def summary(self) -> Dict[str, Any]:
        return {
            "plan_date": self.reference_date.isoformat(),
            "subject_count": len(self.subject_facts),
            "total_budget_minutes": self.total_budget_minutes,
            "remaining_budget_minutes": round(self.remaining_budget_minutes, 1),
            "plan_items_count": len(self.plan_items),
            "fired_rules": self.get_fired_rules(),
        }
