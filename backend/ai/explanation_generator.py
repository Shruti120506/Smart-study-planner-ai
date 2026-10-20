"""
Smart Study Planner AI – Explanation Generator (Phase 3)

Turns raw rule-firing events into human-readable, structured explanations
that can be shown to the student and used during a college viva.

Each explanation contains:
  - rule_id           : which rule fired
  - rule_name         : human-readable rule name
  - conditions_matched: which fact values triggered the rule
  - action_taken      : what the engine decided to do
  - why               : plain-English explanation paragraph
"""

from typing import Dict, Any, List


class ExplanationGenerator:
    """
    Converts rule-firing events into structured explanation objects.
    Stateless – every method is pure given its arguments.
    """

    # Maps internal priority tokens to friendly labels
    _PRIORITY_LABELS = {
        "CRITICAL": "⚠️  CRITICAL  – Exam is imminent or overdue",
        "HIGH":     "🔴 HIGH      – Urgent study needed soon",
        "MEDIUM":   "🟡 MEDIUM    – Steady progress required",
        "LOW":      "🟢 LOW       – Minor revision is enough",
    }

    # Maps session type tokens to friendly descriptions
    _SESSION_LABELS = {
        "emergency_cram":   "Emergency Cram (very short, high-intensity bursts)",
        "new_concept":      "New Concept Study (learn remaining syllabus units)",
        "revision":         "Revision (review already-covered material)",
        "practice_problems":"Practice Problems (apply knowledge to exercises)",
    }

    # -----------------------------------------------------------------------

    def generate(self,
                 rule: Dict,
                 facts: Dict[str, Any],
                 allocated_minutes: float) -> Dict[str, Any]:
        """
        Build a full explanation for one rule-firing event.

        Parameters
        ----------
        rule              : The rule dict from knowledge_base.RULES
        facts             : The SubjectFacts.to_dict() snapshot at time of firing
        allocated_minutes : How many minutes were actually allocated

        Returns
        -------
        A structured explanation dict ready to embed in the API response.
        """
        action = rule["action"]
        subject_priority = action.get("subject_priority", "MEDIUM")
        session_type = action.get("session_type", "new_concept")

        # Fill the template placeholders with actual fact values
        why_text = self._render_template(rule["explanation"], facts)

        # Build condition summary from facts
        conditions_matched = self._summarise_conditions(facts)

        # Build actionable student-friendly recommendation
        recommendation = self._build_recommendation(facts, action, why_text)

        return {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "subject_id": facts.get("subject_id"),
            "subject_name": facts.get("subject_name", "General"),
            "conditions_matched": conditions_matched,
            "action_taken": {
                "subject_priority": subject_priority,
                "priority_label": self._PRIORITY_LABELS.get(subject_priority, subject_priority),
                "session_type": session_type,
                "session_label": self._SESSION_LABELS.get(session_type, session_type),
                "allocated_minutes": round(allocated_minutes, 0),
                "adjustment_factor": action.get("adjustment_factor", 1.0),
            },
            "why": why_text,
            "recommendation": recommendation,
        }

    # -----------------------------------------------------------------------

    def generate_plan_summary(self,
                              plan_items: List[Dict],
                              wm_summary: Dict) -> Dict[str, Any]:
        """
        Produce a top-level narrative summary of the entire daily plan.
        """
        total_allocated = sum(item.get("allocated_minutes", 0) for item in plan_items)
        budget = wm_summary.get("total_budget_minutes", 0)
        remaining = wm_summary.get("remaining_budget_minutes", 0)

        priority_counts = {}
        for item in plan_items:
            p = item.get("priority", "MEDIUM")
            priority_counts[p] = priority_counts.get(p, 0) + 1

        critical = priority_counts.get("CRITICAL", 0)
        high = priority_counts.get("HIGH", 0)

        if critical > 0:
            urgency_note = (
                f"⚠️  {critical} subject(s) are in CRITICAL status – focus on these first!"
            )
        elif high > 0:
            urgency_note = (
                f"🔴 {high} subject(s) need HIGH-priority attention today."
            )
        else:
            urgency_note = "🟡 No critical deadlines today – maintain steady progress."

        return {
            "plan_date": wm_summary.get("plan_date"),
            "total_subjects_planned": len(plan_items),
            "total_budget_minutes": round(budget, 0),
            "total_allocated_minutes": round(total_allocated, 0),
            "remaining_free_minutes": round(remaining, 0),
            "priority_breakdown": priority_counts,
            "urgency_note": urgency_note,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _render_template(template: str, facts: Dict[str, Any]) -> str:
        """
        Safe string formatting: replace known placeholders, leave
        unrecognised ones as-is.
        """
        safe_facts = {
            "subject_name": facts.get("subject_name", "this subject"),
            "days_remaining": facts.get("days_remaining", "?"),
            "completion_pct": facts.get("completion_pct", 0.0),
            "remaining_units": facts.get("remaining_units", 0),
            "difficulty_level": facts.get("difficulty_level", "medium"),
            "fatigue_level": facts.get("fatigue_level", "medium"),
            "daily_available_hours": facts.get("daily_available_hours", 4.0),
        }
        try:
            return template.format(**safe_facts)
        except (KeyError, ValueError):
            return template  # Return unformatted if something unexpected occurs

    @staticmethod
    def _summarise_conditions(facts: Dict[str, Any]) -> List[str]:
        """
        Convert the fact snapshot into a readable list of
        'condition: value' strings (shown in the explanation).
        """
        lines = []
        days = facts.get("days_remaining")
        if days is not None:
            if days < 0:
                lines.append(f"Exam overdue by {abs(days)} day(s)")
            else:
                lines.append(f"Days until exam: {days}")

        pct = facts.get("completion_pct")
        if pct is not None:
            lines.append(f"Syllabus completion: {pct:.0f}%")

        lines.append(f"Difficulty: {facts.get('difficulty_level', 'medium')}")
        lines.append(f"Fatigue level: {facts.get('fatigue_level', 'medium')}")
        lines.append(f"Available study hours/day: {facts.get('daily_available_hours', 4.0)}")

        return lines

    @staticmethod
    def _build_recommendation(facts: Dict[str, Any], action: Dict[str, Any], why_text: str) -> str:
        """Generate a direct, actionable recommendation tailored to the student."""
        days = facts.get("days_remaining", 9999)
        rem_units = facts.get("remaining_units", 0)
        session_type = action.get("session_type", "new_concept")
        priority = action.get("subject_priority", "MEDIUM")

        if days < 0:
            return "Exam date has passed. Focus on backlog review and problem sets."
        elif days <= 3 and rem_units > 0:
            return f"Exam in {days} day(s). Prioritize high-yield concepts and formula revision today."
        elif rem_units == 0:
            return "Syllabus complete! Practice previous exam papers and light flashcard review."
        elif priority == "HIGH" or priority == "CRITICAL":
            return f"Dedicate your peak focus hours to completing the remaining {rem_units} chapter(s)."
        elif session_type == "revision":
            return "Review key summary notes from covered chapters to strengthen memory retention."
        else:
            return f"Maintain a consistent pace: study 1 chapter at a time with short 5–10 min breaks."
