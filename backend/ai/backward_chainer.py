"""
Smart Study Planner AI – Backward Chainer (Phase 3, revised)

Backward chaining = "goal-driven" reasoning.

Goal: "Can the student complete the remaining syllabus of subject X
       before its exam, given the available daily study hours?"

Algorithm:
  1. Start with the GOAL: cover all remaining_units before the exam.
  2. Estimate required study hours:
       required_hours = remaining_units × hours_per_unit
       hours_per_unit depends on difficulty: easy=1h, medium=1.5h, hard=2h

  3. Estimate fairly-allocated study hours until the exam:
       The student has `daily_available_hours` total per day shared across
       ALL active subjects.  Each subject receives a weighted share whose
       weights sum to exactly 1.0 across subjects – so the daily budget is
       never double-counted.

       weight(subject_i)   = PRIORITY_WEIGHT[priority_i]
       normalised_share(i) = weight(i) / sum(all weights)
       hours_per_day(i)    = daily_available_hours × normalised_share(i)
       available_hours(i)  = days_remaining(i) × hours_per_day(i)

       This means:
         • A subject with more days gets more *total* hours – correctly.
         • No matter how many subjects exist, their per-day slices add up to
           at most daily_available_hours – never inflated.
         • A CRITICAL subject gets a proportionally larger slice than a LOW
           one, but the total stays bounded.

  4. Check: required_hours ≤ available_hours?
       → YES → Goal is achievable.  Report required daily commitment.
       → NO  → Goal is NOT achievable with current pace.
                Suggest adjustments:
                  a) Increase daily hours
                  b) Reduce units scope (focus on key units)
                  c) Reduce hours_per_unit by studying smarter

  5. Also explain WHICH sub-goals were checked (transparency for viva).

Naming clarification (shown in API response):
  available_study_hours  = TOTAL hours available for this subject across
                           ALL remaining days until its exam.
                           (NOT hours per day – that is hours_per_day_for_subject)
  required_study_hours   = total hours needed to finish remaining units.
  deficit_hours          = max(0, required - available) total shortfall.
"""

from typing import Dict, List, Any, Optional
from datetime import date

from .working_memory import WorkingMemory, SubjectFacts
from .explanation_generator import ExplanationGenerator


# ── Hours needed to complete one syllabus unit, by difficulty ────────────────
HOURS_PER_UNIT: Dict[str, float] = {
    "easy":   1.0,
    "medium": 1.5,
    "hard":   2.0,
}

# ── Unnormalised priority weights (higher = more of the daily budget) ────────
# These are *relative* weights; they are normalised at runtime so the total
# daily allocation always sums to exactly daily_available_hours.
PRIORITY_WEIGHT: Dict[str, float] = {
    "CRITICAL": 4.0,   # 4× the weight of a LOW subject
    "HIGH":     2.5,
    "MEDIUM":   1.5,
    "LOW":      1.0,
}


def _compute_normalised_shares(priority_map: Dict[int, str],
                               all_subject_ids: List[int]) -> Dict[int, float]:
    """
    Given priority labels for each subject, compute normalised share
    fractions that sum to exactly 1.0.

    Subjects absent from priority_map are treated as MEDIUM.
    """
    weights = {
        sid: PRIORITY_WEIGHT.get(priority_map.get(sid, "MEDIUM"), 1.5)
        for sid in all_subject_ids
    }
    total_weight = sum(weights.values()) or 1.0  # avoid div-by-zero
    return {sid: w / total_weight for sid, w in weights.items()}


class BackwardChainer:
    """
    Goal-driven reasoning: checks whether study goals are achievable and
    explains deficits or surpluses.

    Key design principle:
      The student's daily_available_hours is treated as a SINGLE budget shared
      across subjects.  Shares are normalised so they always sum to 1.0 – no
      subject double-counts another subject's time.
    """

    def __init__(self):
        self.explainer = ExplanationGenerator()

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def check_goals(self, wm: WorkingMemory,
                    forward_plan: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Check whether study goals are achievable for every subject in `wm`.

        Parameters
        ----------
        wm            : The WorkingMemory instance (subjects + preferences).
        forward_plan  : Optional list of plan_items from ForwardChainer;
                        used to determine each subject's priority for budget
                        share computation.

        Returns
        -------
        {
          "goal_results"       : [ { per-subject analysis } ],
          "overall_feasible"   : bool,
          "overall_explanation": str,
          "daily_budget_hours" : float   – the student's total daily study hours
        }
        """
        if not wm.subject_facts:
            return {
                "goal_results": [],
                "overall_feasible": True,
                "overall_explanation": "No subjects to analyse.",
                "daily_budget_hours": wm.preferences.get("daily_available_hours", 4.0),
            }

        # ── Build priority lookup from forward plan (if provided) ────────────
        priority_map: Dict[int, str] = {}
        if forward_plan:
            for item in forward_plan:
                sid = item.get("subject_id")
                if sid is not None:
                    priority_map[sid] = item.get("priority", "MEDIUM")

        # ── Compute normalised shares (sums to 1.0 across all subjects) ──────
        all_ids = [sf.subject_id for sf in wm.subject_facts]
        normalised_shares = _compute_normalised_shares(priority_map, all_ids)

        daily_budget = float(wm.preferences.get("daily_available_hours", 4.0))

        results: List[Dict] = []
        for sf in wm.subject_facts:
            result = self._check_single_goal(
                sf, daily_budget, normalised_shares, priority_map
            )
            results.append(result)

        # ── Overall feasibility ──────────────────────────────────────────────
        all_feasible = all(r["is_feasible"] for r in results)
        infeasible = [r for r in results if not r["is_feasible"]]

        if all_feasible:
            overall_explanation = (
                "✅ All study goals are achievable with the current daily hours "
                "and the available time before each exam."
            )
        else:
            names = ", ".join(r["subject_name"] for r in infeasible)
            overall_explanation = (
                f"❌ {len(infeasible)} subject(s) cannot be fully covered in the "
                f"available time: {names}. See individual recommendations below."
            )

        return {
            "goal_results": results,
            "overall_feasible": all_feasible,
            "overall_explanation": overall_explanation,
            "daily_budget_hours": daily_budget,
        }

    # -----------------------------------------------------------------------
    # Single-subject goal check
    # -----------------------------------------------------------------------

    def _check_single_goal(self,
                            sf: SubjectFacts,
                            daily_budget: float,
                            normalised_shares: Dict[int, float],
                            priority_map: Dict[int, str]) -> Dict[str, Any]:
        """Run backward chaining for one subject."""

        subject_priority = priority_map.get(sf.subject_id, "MEDIUM")
        share_fraction = normalised_shares.get(sf.subject_id, 1.0)

        # ── Sub-goal 1: How much study time is required? ─────────────────────
        hours_per_unit = HOURS_PER_UNIT.get(sf.difficulty_level, 1.5)
        required_hours = sf.remaining_units * hours_per_unit

        # ── Sub-goal 2: How much study time is available? ────────────────────
        # hours_per_day_for_subject = student's total daily budget × this
        # subject's normalised share.  Because shares sum to 1.0, the sum of
        # all subjects' hours_per_day equals exactly daily_budget – no inflation.
        if sf.days_remaining < 0:
            available_hours = 0.0
            hours_per_day_for_subject = 0.0
        else:
            hours_per_day_for_subject = daily_budget * share_fraction
            available_hours = sf.days_remaining * hours_per_day_for_subject

        # ── Goal check ───────────────────────────────────────────────────────
        deficit_hours = max(0.0, required_hours - available_hours)
        surplus_hours = max(0.0, available_hours - required_hours)
        is_feasible = deficit_hours == 0.0

        # ── Checked sub-goals (for transparency / viva) ──────────────────────
        sub_goals_checked = self._build_sub_goals(
            sf, required_hours, available_hours,
            hours_per_unit, share_fraction, hours_per_day_for_subject,
            subject_priority, daily_budget
        )

        # ── Recommendations ──────────────────────────────────────────────────
        recommendations = []
        if not is_feasible:
            recommendations = self._compute_recommendations(
                sf, required_hours, deficit_hours,
                hours_per_day=hours_per_day_for_subject
            )

        return {
            "subject_id": sf.subject_id,
            "subject_name": sf.subject_name,
            "difficulty_level": sf.difficulty_level,
            "days_remaining": sf.days_remaining,
            "remaining_units": sf.remaining_units,
            "completion_pct": sf.completion_pct,
            # ── Time accounting (clear names) ────────────────────────────────
            "required_study_hours": round(required_hours, 2),
            "hours_per_day_for_subject": round(hours_per_day_for_subject, 2),
            "available_study_hours": round(available_hours, 2),
            # available_study_hours = TOTAL hours across all remaining days
            # (days_remaining × hours_per_day_for_subject)
            "deficit_hours": round(deficit_hours, 2),
            "surplus_hours": round(surplus_hours, 2),
            "is_feasible": is_feasible,
            # ── Budget share metadata ────────────────────────────────────────
            "subject_priority_used": subject_priority,
            "normalised_share_fraction": round(share_fraction, 4),
            "daily_budget_hours": round(daily_budget, 2),
            # ── Reasoning chain ──────────────────────────────────────────────
            "sub_goals_checked": sub_goals_checked,
            "recommendations": recommendations,
            "explanation": self._feasibility_explanation(
                sf, is_feasible, required_hours, available_hours,
                deficit_hours, surplus_hours
            ),
        }

    # -----------------------------------------------------------------------
    # Sub-goal chain (shown as reasoning steps)
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_sub_goals(sf: SubjectFacts,
                         required_hours: float,
                         available_hours: float,
                         hours_per_unit: float,
                         share_fraction: float,
                         hours_per_day_for_subject: float,
                         subject_priority: str,
                         daily_budget: float) -> List[Dict]:
        """Build the list of sub-goals that were evaluated (viva-friendly)."""
        return [
            {
                "step": 1,
                "goal": "Determine required study hours",
                "reasoning": (
                    f"{sf.remaining_units} remaining unit(s) × "
                    f"{hours_per_unit}h per unit ({sf.difficulty_level} difficulty) "
                    f"= {required_hours:.2f}h required in total"
                ),
                "result": f"{required_hours:.2f}h needed",
            },
            {
                "step": 2,
                "goal": "Determine daily hours allocated to this subject",
                "reasoning": (
                    f"{daily_budget}h/day total budget × "
                    f"{share_fraction:.1%} normalised share "
                    f"(priority={subject_priority}, weights normalised so all "
                    f"subjects sum to 100%) = {hours_per_day_for_subject:.2f}h/day "
                    f"for this subject"
                ),
                "result": f"{hours_per_day_for_subject:.2f}h/day available for this subject",
            },
            {
                "step": 3,
                "goal": "Determine total available hours before exam",
                "reasoning": (
                    f"{sf.days_remaining} day(s) remaining × "
                    f"{hours_per_day_for_subject:.2f}h/day "
                    f"= {available_hours:.2f}h total available"
                ),
                "result": (
                    "YES – goal is achievable"
                    if required_hours <= available_hours
                    else "NO – time deficit exists"
                ),
            },
        ]

    # -----------------------------------------------------------------------
    # Recommendation engine
    # -----------------------------------------------------------------------

    @staticmethod
    def _compute_recommendations(sf: SubjectFacts,
                                 required_hours: float,
                                 deficit_hours: float,
                                 hours_per_day: float) -> List[str]:
        """Generate actionable suggestions when a goal is not feasible."""
        recs = []

        # 1. How many extra hours/day are needed?
        if sf.days_remaining > 0:
            extra_per_day = deficit_hours / sf.days_remaining
            recs.append(
                f"Increase daily study for {sf.subject_name} by "
                f"{extra_per_day:.1f}h/day (total extra needed: {deficit_hours:.1f}h)."
            )
        else:
            recs.append(
                f"Exam for {sf.subject_name} is overdue. "
                "Focus on any remaining assessments or practicals instead."
            )

        # 2. Scope reduction
        if sf.remaining_units > 1:
            recs.append(
                f"Prioritise the {min(sf.remaining_units, 3)} most important units "
                f"of {sf.subject_name} and use concise notes for the rest."
            )

        # 3. Study-smarter suggestion
        recs.append(
            f"Use active recall and spaced repetition to cut effective "
            f"study time by up to 30% for {sf.subject_name}."
        )

        return recs

    # -----------------------------------------------------------------------

    @staticmethod
    def _feasibility_explanation(sf: SubjectFacts,
                                 is_feasible: bool,
                                 required: float,
                                 available: float,
                                 deficit: float,
                                 surplus: float) -> str:
        name = sf.subject_name
        if sf.days_remaining < 0:
            return (
                f"❌ Goal FAILED for {name}: the exam date has already passed. "
                "No study time can be recovered."
            )
        if is_feasible:
            return (
                f"✅ Goal ACHIEVED for {name}: {required:.2f}h required ≤ "
                f"{available:.2f}h available (across all remaining days). "
                f"You have {surplus:.2f}h of buffer."
            )
        else:
            return (
                f"❌ Goal FAILED for {name}: {required:.2f}h required but only "
                f"{available:.2f}h available (across all remaining days). "
                f"Time deficit is {deficit:.2f}h. "
                "See recommendations above to resolve this shortfall."
            )
