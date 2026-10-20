"""
Smart Study Planner AI – Forward Chainer (Phase 3)

Forward chaining = "data-driven" reasoning.

Algorithm:
  1. Load all SubjectFacts into Working Memory (already done by caller).
  2. Sort subjects by urgency (overdue first, then fewest days remaining).
  3. For each subject, evaluate every rule in priority order.
  4. The FIRST rule whose condition evaluates to True fires.
     (Conflict resolution: priority order; a rule may not fire on the
      same subject twice in one planning cycle.)
  5. Compute the allocated study minutes using:
       base_minutes  = focus_span_minutes          (from preferences)
       adj_minutes   = base_minutes × adjustment_factor  (from rule)
       if fatigue==high: adj_minutes × 0.8          (extra fatigue cut)
  6. Deduct from the daily budget; stop when budget is exhausted.
  7. Return plan_items, explanations, and the working-memory summary.
"""

from typing import Dict, List, Optional, Any

from .knowledge_base import get_rules
from .working_memory import WorkingMemory, SubjectFacts
from .explanation_generator import ExplanationGenerator


class ForwardChainer:
    """
    Data-driven rule evaluation that derives a daily study plan.
    """

    def __init__(self):
        self.rules = get_rules()            # sorted by priority
        self.explainer = ExplanationGenerator()

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def generate_plan(self, wm: WorkingMemory) -> Dict[str, Any]:
        """
        Run forward chaining on all subjects in `wm`.

        Returns
        -------
        {
          "plan_items"   : [ { subject info + rule info + allocated_minutes } ],
          "explanations" : [ ExplanationGenerator.generate() output per item ],
          "summary"      : WorkingMemory.summary(),
          "plan_summary" : ExplanationGenerator.generate_plan_summary() output,
        }
        """
        if not wm.subject_facts:
            return self._empty_plan(wm)

        # Sort subjects by urgency (most urgent first)
        ordered = self._sort_by_urgency(wm.subject_facts)

        plan_items: List[Dict] = []
        explanations: List[Dict] = []

        for sf in ordered:
            if not wm.has_budget(minimum_minutes=10.0):
                break  # Daily budget exhausted – stop planning

            facts = sf.to_dict()
            matched_rule = self._match_rule(sf, wm)

            if matched_rule is None:
                continue   # No rule matched (shouldn't happen – R14 is catch-all)

            # ── Compute session duration ────────────────────────────────────
            allocated = self._compute_allocated_minutes(sf, matched_rule)
            actual_allocated = wm.allocate_minutes(allocated)

            if actual_allocated < 5:
                break  # Too little budget left; skip tiny sessions

            # ── Mark rule as fired ─────────────────────────────────────────
            wm.mark_fired(sf.subject_id, matched_rule["id"])

            # ── Build plan item ────────────────────────────────────────────
            action = matched_rule["action"]
            item = {
                "subject_id": sf.subject_id,
                "subject_name": sf.subject_name,
                "priority": action["subject_priority"],
                "session_type": action["session_type"],
                "allocated_minutes": round(actual_allocated),
                "break_minutes": self._break_duration(sf),
                "recommended_time_slot": sf.preferred_time_of_day,
                "fired_rule_id": matched_rule["id"],
                "session_title": (
                    f"{action['label']} – {sf.subject_name}"
                ),
                "days_until_exam": sf.days_remaining,
                "completion_pct": sf.completion_pct,
            }
            wm.add_plan_item(item)
            plan_items.append(item)

            # ── Generate explanation ───────────────────────────────────────
            explanation = self.explainer.generate(matched_rule, facts, actual_allocated)
            explanations.append(explanation)

        wm_summary = wm.summary()
        plan_summary = self.explainer.generate_plan_summary(plan_items, wm_summary)

        return {
            "plan_items": plan_items,
            "explanations": explanations,
            "summary": wm_summary,
            "plan_summary": plan_summary,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _match_rule(self, sf: SubjectFacts, wm: WorkingMemory) -> Optional[Dict]:
        """
        Evaluate rules in priority order; return the first one that:
          1. Has NOT already fired on this subject this cycle.
          2. Passes its condition against the subject's facts.
        """
        facts = sf.to_dict()
        for rule in self.rules:
            if wm.already_fired(sf.subject_id, rule["id"]):
                continue
            try:
                if rule["conditions"](facts):
                    return rule
            except Exception:
                continue  # Guard against malformed rule conditions
        return None

    def _compute_allocated_minutes(self, sf: SubjectFacts, rule: Dict) -> float:
        """
        Compute how many minutes to allocate for this session:
          base     = student's focus_span_minutes
          adjusted = base × rule.adjustment_factor
          if fatigue==high: ×0.8 (additional cut)
        Minimum session: 10 minutes.
        """
        base = float(sf.focus_span_minutes)
        adj_factor = rule["action"].get("adjustment_factor", 0.6)
        allocated = base * adj_factor

        if sf.fatigue_level == "high":
            allocated *= 0.8

        return max(10.0, round(allocated, 1))

    @staticmethod
    def _break_duration(sf: SubjectFacts) -> int:
        """Return break duration in minutes based on fatigue."""
        if sf.fatigue_level == "high":
            return 15   # more frequent breaks
        elif sf.fatigue_level == "low":
            return 5
        return 10

    @staticmethod
    def _sort_by_urgency(subject_facts: List[SubjectFacts]) -> List[SubjectFacts]:
        """
        Sort subjects so the most urgent appear first:
          1. Overdue exams (days_remaining < 0)
          2. Fewest days remaining (ascending)
          3. Highest completion deficit (100 - pct)
          4. Hardest difficulty
        """
        difficulty_rank = {"hard": 0, "medium": 1, "easy": 2}

        def urgency_key(sf: SubjectFacts):
            days = sf.days_remaining
            # Overdue = very negative days → should sort first
            urgency_days = days if days >= 0 else -99999
            deficit = 100.0 - sf.completion_pct
            diff_rank = difficulty_rank.get(sf.difficulty_level, 1)
            return (urgency_days, -deficit, diff_rank)

        return sorted(subject_facts, key=urgency_key)

    @staticmethod
    def _empty_plan(wm: WorkingMemory) -> Dict:
        return {
            "plan_items": [],
            "explanations": [],
            "summary": wm.summary(),
            "plan_summary": {
                "plan_date": wm.reference_date.isoformat(),
                "total_subjects_planned": 0,
                "total_budget_minutes": wm.total_budget_minutes,
                "total_allocated_minutes": 0,
                "remaining_free_minutes": wm.total_budget_minutes,
                "priority_breakdown": {},
                "urgency_note": "No subjects found. Add subjects to generate a study plan.",
            },
        }
