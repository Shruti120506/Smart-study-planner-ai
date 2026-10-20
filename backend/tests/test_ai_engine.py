"""
Phase 3 – AI Engine Tests

Covers:
  - Knowledge base structure and rule retrieval
  - WorkingMemory fact computation
  - Forward chaining: plan generation, urgency ordering, time allocation,
    fatigue reduction, daily budget cap, empty-subject safety
  - Backward chaining: feasible goals, infeasible goals, overdue subject,
    single-subject filtering
  - Explanation generator: template rendering, condition summary
  - Conflict resolution: rule does not re-fire on same subject
  - API endpoints: /api/ai/plan, /api/ai/goals, /api/ai/rules, /api/ai/explain
"""

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

# ── Path setup (mirrors existing test files) ───────────────────────────────
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(TESTS_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import create_app
    from backend.ai.knowledge_base import get_rules, get_rule_by_id
    from backend.ai.working_memory import WorkingMemory, SubjectFacts
    from backend.ai.forward_chainer import ForwardChainer
    from backend.ai.backward_chainer import BackwardChainer
    from backend.ai.explanation_generator import ExplanationGenerator
    from backend.database.db import init_db
except ImportError:
    from app import create_app
    from ai.knowledge_base import get_rules, get_rule_by_id
    from ai.working_memory import WorkingMemory, SubjectFacts
    from ai.forward_chainer import ForwardChainer
    from ai.backward_chainer import BackwardChainer
    from ai.explanation_generator import ExplanationGenerator
    from database.db import init_db


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

TODAY = date.today()

def _subject(name="Maths", difficulty="medium", days_ahead=7,
             total=5, completed=2, exam=True):
    """Create a minimal subject dict."""
    return {
        "id": 1,
        "name": name,
        "difficulty_level": difficulty,
        "target_grade": "A",
        "exam_date": (TODAY + timedelta(days=days_ahead)).isoformat() if exam else None,
        "syllabus_units_total": total,
        "units_completed": completed,
    }

def _prefs(hours=4.0, fatigue="medium", span=45, time_of_day="morning"):
    return {
        "daily_available_hours": hours,
        "fatigue_level": fatigue,
        "focus_span_minutes": span,
        "preferred_time_of_day": time_of_day,
    }


# ===========================================================================
# 1. Knowledge Base Tests
# ===========================================================================

class KnowledgeBaseTestCase(unittest.TestCase):
    """Tests for the rule knowledge base."""

    def test_rules_are_sorted_by_priority(self):
        """Rules returned by get_rules() are sorted ascending by priority."""
        rules = get_rules()
        priorities = [r["priority"] for r in rules]
        self.assertEqual(priorities, sorted(priorities))

    def test_every_rule_has_required_fields(self):
        """Each rule must have id, name, priority, conditions, action, explanation."""
        required = {"id", "name", "priority", "conditions", "action", "explanation"}
        for rule in get_rules():
            missing = required - set(rule.keys())
            self.assertEqual(missing, set(), f"Rule {rule['id']} missing: {missing}")

    def test_rule_ids_are_unique(self):
        """All rule IDs must be unique."""
        ids = [r["id"] for r in get_rules()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_rule_by_id(self):
        """get_rule_by_id returns correct rule and None for unknown id."""
        r = get_rule_by_id("R01")
        self.assertIsNotNone(r)
        self.assertEqual(r["id"], "R01")

        missing = get_rule_by_id("ZZZZ")
        self.assertIsNone(missing)

    def test_r01_fires_on_overdue_exam(self):
        """R01 should fire when days_remaining is negative."""
        r = get_rule_by_id("R01")
        self.assertTrue(r["conditions"]({"days_remaining": -3}))
        self.assertFalse(r["conditions"]({"days_remaining": 1}))

    def test_r02_fires_on_imminent_exam(self):
        """R02 fires when exam is in 0-2 days and syllabus incomplete."""
        r = get_rule_by_id("R02")
        self.assertTrue(r["conditions"]({
            "days_remaining": 1,
            "completion_pct": 50.0,
            "units_completed": 2,
            "syllabus_units_total": 5,
        }))
        # Should NOT fire if syllabus is 100% done
        self.assertFalse(r["conditions"]({
            "days_remaining": 1,
            "completion_pct": 100.0,
            "units_completed": 5,
            "syllabus_units_total": 5,
        }))

    def test_r13_fires_on_complete_syllabus(self):
        """R13 fires when completion is >= 100%."""
        r = get_rule_by_id("R13")
        self.assertTrue(r["conditions"]({
            "completion_pct": 100.0,
            "units_completed": 5,
            "syllabus_units_total": 5,
        }))

    def test_r14_is_catch_all(self):
        """R14 (default) always returns True."""
        r = get_rule_by_id("R14")
        self.assertTrue(r["conditions"]({}))
        self.assertTrue(r["conditions"]({"days_remaining": 999}))

    def test_action_fields_present(self):
        """Every rule's action dict has subject_priority and session_type."""
        for rule in get_rules():
            self.assertIn("subject_priority", rule["action"],
                          f"Rule {rule['id']} missing subject_priority")
            self.assertIn("session_type", rule["action"],
                          f"Rule {rule['id']} missing session_type")


# ===========================================================================
# 2. Working Memory Tests
# ===========================================================================

class WorkingMemoryTestCase(unittest.TestCase):
    """Tests for SubjectFacts and WorkingMemory."""

    def test_subject_facts_completion_pct(self):
        """completion_pct computed correctly."""
        sf = SubjectFacts(
            _subject(total=5, completed=3),
            _prefs(),
        )
        self.assertAlmostEqual(sf.completion_pct, 60.0, places=1)
        self.assertEqual(sf.remaining_units, 2)

    def test_subject_facts_days_remaining(self):
        """days_remaining computed from exam_date vs today."""
        sf = SubjectFacts(_subject(days_ahead=5), _prefs())
        self.assertEqual(sf.days_remaining, 5)

    def test_subject_facts_overdue(self):
        """days_remaining is negative for past exam date."""
        sub = _subject()
        sub["exam_date"] = (TODAY - timedelta(days=3)).isoformat()
        sf = SubjectFacts(sub, _prefs())
        self.assertEqual(sf.days_remaining, -3)

    def test_subject_facts_no_exam_date(self):
        """days_remaining defaults to 9999 when no exam_date."""
        sf = SubjectFacts(_subject(exam=False), _prefs())
        self.assertEqual(sf.days_remaining, 9999)

    def test_subject_facts_100pct_complete(self):
        """100% complete subject has remaining_units == 0."""
        sf = SubjectFacts(_subject(total=4, completed=4), _prefs())
        self.assertAlmostEqual(sf.completion_pct, 100.0, places=1)
        self.assertEqual(sf.remaining_units, 0)

    def test_working_memory_budget(self):
        """WorkingMemory initialises budget from preferences correctly."""
        subjects = [_subject()]
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        self.assertAlmostEqual(wm.total_budget_minutes, 240.0, places=1)

    def test_working_memory_allocate_minutes(self):
        """allocate_minutes reduces the remaining budget correctly."""
        wm = WorkingMemory([_subject()], _prefs(hours=2.0))  # 120 min budget
        allocated = wm.allocate_minutes(50.0)
        self.assertAlmostEqual(allocated, 50.0, places=1)
        self.assertAlmostEqual(wm.remaining_budget_minutes, 70.0, places=1)

    def test_working_memory_allocate_caps_at_budget(self):
        """allocate_minutes never exceeds remaining budget."""
        wm = WorkingMemory([_subject()], _prefs(hours=0.5))  # 30 min budget
        allocated = wm.allocate_minutes(200.0)  # more than budget
        self.assertAlmostEqual(allocated, 30.0, places=1)
        self.assertAlmostEqual(wm.remaining_budget_minutes, 0.0, places=1)

    def test_working_memory_fired_rules_tracking(self):
        """Fired rule tracking prevents repeated entries."""
        wm = WorkingMemory([_subject()], _prefs())
        wm.mark_fired(1, "R03")
        self.assertTrue(wm.already_fired(1, "R03"))
        self.assertFalse(wm.already_fired(1, "R04"))

    def test_working_memory_empty_subjects(self):
        """WorkingMemory with no subjects is safe."""
        wm = WorkingMemory([], _prefs())
        self.assertEqual(len(wm.subject_facts), 0)


# ===========================================================================
# 3. Forward Chaining Tests
# ===========================================================================

class ForwardChainingTestCase(unittest.TestCase):
    """Tests for the ForwardChainer."""

    def setUp(self):
        self.fc = ForwardChainer()

    def test_plan_generated_for_single_subject(self):
        """ForwardChainer produces at least one plan item for a normal subject."""
        wm = WorkingMemory([_subject(days_ahead=7)], _prefs())
        result = self.fc.generate_plan(wm)
        self.assertGreater(len(result["plan_items"]), 0)
        self.assertGreater(len(result["explanations"]), 0)

    def test_plan_empty_when_no_subjects(self):
        """Empty subject list produces empty plan."""
        wm = WorkingMemory([], _prefs())
        result = self.fc.generate_plan(wm)
        self.assertEqual(result["plan_items"], [])
        self.assertIn("No subjects", result["plan_summary"]["urgency_note"])

    def test_overdue_subject_is_critical(self):
        """A subject whose exam date has passed gets CRITICAL priority."""
        sub = _subject(name="Physics", difficulty="hard")
        sub["exam_date"] = (TODAY - timedelta(days=1)).isoformat()
        wm = WorkingMemory([sub], _prefs())
        result = self.fc.generate_plan(wm)
        item = result["plan_items"][0]
        self.assertEqual(item["priority"], "CRITICAL")
        self.assertEqual(item["fired_rule_id"], "R01")

    def test_imminent_exam_is_critical(self):
        """Exam in 1 day with incomplete syllabus → CRITICAL."""
        sub = _subject(name="Chemistry", days_ahead=1, completed=2, total=5)
        wm = WorkingMemory([sub], _prefs())
        result = self.fc.generate_plan(wm)
        item = result["plan_items"][0]
        self.assertEqual(item["priority"], "CRITICAL")

    def test_complete_syllabus_gets_low_priority(self):
        """A subject with 100% completion fires R13 (LOW priority, revision)."""
        sub = _subject(name="History", total=4, completed=4, days_ahead=15)
        wm = WorkingMemory([sub], _prefs())
        result = self.fc.generate_plan(wm)
        item = result["plan_items"][0]
        self.assertEqual(item["priority"], "LOW")
        self.assertEqual(item["session_type"], "revision")

    def test_urgency_ordering_puts_closest_exam_first(self):
        """Subject with fewer days remaining appears first in the plan."""
        sub_urgent = {**_subject(name="Urgent", days_ahead=2, completed=1, total=5), "id": 1}
        sub_distant = {**_subject(name="Distant", days_ahead=20, completed=1, total=5), "id": 2}
        wm = WorkingMemory([sub_distant, sub_urgent], _prefs())
        result = self.fc.generate_plan(wm)
        first_name = result["plan_items"][0]["subject_name"]
        self.assertEqual(first_name, "Urgent")

    def test_fatigue_reduces_session_length(self):
        """High fatigue produces shorter sessions than low fatigue."""
        sub = _subject(days_ahead=5)
        wm_high = WorkingMemory([sub], _prefs(fatigue="high", span=60))
        wm_low = WorkingMemory([sub], _prefs(fatigue="low", span=60))
        res_high = self.fc.generate_plan(wm_high)
        res_low = self.fc.generate_plan(wm_low)
        mins_high = res_high["plan_items"][0]["allocated_minutes"]
        mins_low = res_low["plan_items"][0]["allocated_minutes"]
        self.assertLessEqual(mins_high, mins_low)

    def test_daily_budget_never_exceeded(self):
        """Total allocated minutes never exceed the daily budget."""
        subjects = []
        for i in range(8):
            s = _subject(name=f"Subject{i}", days_ahead=3+i, completed=1, total=6)
            s["id"] = i + 1
            subjects.append(s)
        wm = WorkingMemory(subjects, _prefs(hours=2.0))   # tight 120-min budget
        result = self.fc.generate_plan(wm)
        total = sum(item["allocated_minutes"] for item in result["plan_items"])
        self.assertLessEqual(total, wm.total_budget_minutes + 1)  # allow 1-min float rounding

    def test_conflict_resolution_rule_not_repeated(self):
        """The same rule does not fire twice on the same subject."""
        sub = _subject(name="CS", days_ahead=4, completed=1, total=5)
        wm = WorkingMemory([sub], _prefs())
        self.fc.generate_plan(wm)
        # Check rule_logs: only one rule per subject
        fired = wm.get_fired_rules()
        self.assertEqual(len(fired.get(sub["id"], [])), 1)

    def test_plan_summary_structure(self):
        """Plan summary has expected keys."""
        wm = WorkingMemory([_subject()], _prefs())
        result = self.fc.generate_plan(wm)
        summary = result["plan_summary"]
        for key in ["plan_date", "total_subjects_planned",
                    "total_budget_minutes", "total_allocated_minutes",
                    "urgency_note"]:
            self.assertIn(key, summary, f"Missing key: {key}")


# ===========================================================================
# 4. Backward Chaining Tests
# ===========================================================================

class BackwardChainingTestCase(unittest.TestCase):
    """Tests for the BackwardChainer – normalised share model."""

    def setUp(self):
        self.bc = BackwardChainer()

    # ── feasibility basics ──────────────────────────────────────────────────

    def test_feasible_goal_single_subject(self):
        """
        Single subject, plenty of time.
        1 easy unit remaining, 30 days.
        required = 1 × 1h = 1h.
        share   = 1/1 = 100% (only subject)
        avail   = 30 × (4 × 1.0) = 120h  >> 1h  → feasible.
        """
        sub = _subject(name="Intro CS", difficulty="easy",
                       days_ahead=30, total=5, completed=4)
        wm = WorkingMemory([sub], _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        self.assertTrue(result["overall_feasible"])
        self.assertTrue(result["goal_results"][0]["is_feasible"])

    def test_infeasible_goal_single_subject(self):
        """
        Single subject, too little time.
        5 hard units, 2 days, 4h/day.
        required = 5 × 2h = 10h.
        share    = 100% (only subject)
        avail    = 2 × 4.0 = 8h  < 10h  → infeasible.
        """
        sub = _subject(name="Advanced Maths", difficulty="hard",
                       days_ahead=2, total=5, completed=0)
        wm = WorkingMemory([sub], _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        self.assertFalse(result["overall_feasible"])
        gr = result["goal_results"][0]
        self.assertFalse(gr["is_feasible"])
        self.assertAlmostEqual(gr["required_study_hours"], 10.0, places=1)
        self.assertAlmostEqual(gr["available_study_hours"], 8.0, places=1)
        self.assertGreater(gr["deficit_hours"], 0)

    def test_overdue_exam_infeasible(self):
        """Overdue subject (negative days_remaining) → available = 0 → infeasible."""
        sub = _subject(name="Overdue Subject", difficulty="medium")
        sub["exam_date"] = (TODAY - timedelta(days=2)).isoformat()
        wm = WorkingMemory([sub], _prefs())
        result = self.bc.check_goals(wm)
        gr = result["goal_results"][0]
        self.assertFalse(gr["is_feasible"])
        self.assertEqual(gr["available_study_hours"], 0.0)
        self.assertEqual(gr["hours_per_day_for_subject"], 0.0)

    def test_empty_subjects_all_feasible(self):
        """No subjects → overall feasible, empty results."""
        wm = WorkingMemory([], _prefs())
        result = self.bc.check_goals(wm)
        self.assertTrue(result["overall_feasible"])
        self.assertEqual(result["goal_results"], [])

    def test_complete_subject_is_feasible(self):
        """100% complete subject → required = 0h → always feasible."""
        sub = _subject(name="Done Subject", total=4, completed=4, days_ahead=3)
        wm = WorkingMemory([sub], _prefs())
        result = self.bc.check_goals(wm)
        gr = result["goal_results"][0]
        self.assertEqual(gr["required_study_hours"], 0.0)
        self.assertTrue(gr["is_feasible"])

    # ── sub-goals and transparency ──────────────────────────────────────────

    def test_sub_goals_are_present(self):
        """Each goal result contains exactly 3 sub-goals."""
        sub = _subject(days_ahead=10)
        wm = WorkingMemory([sub], _prefs())
        result = self.bc.check_goals(wm)
        gr = result["goal_results"][0]
        self.assertIn("sub_goals_checked", gr)
        self.assertEqual(len(gr["sub_goals_checked"]), 3)

    def test_new_fields_present_in_result(self):
        """Result must include the renamed/new fields."""
        sub = _subject(days_ahead=10)
        wm = WorkingMemory([sub], _prefs())
        result = self.bc.check_goals(wm)
        gr = result["goal_results"][0]
        self.assertIn("hours_per_day_for_subject", gr)
        self.assertIn("normalised_share_fraction", gr)
        self.assertIn("daily_budget_hours", gr)

    def test_daily_budget_reported_at_top_level(self):
        """check_goals result includes daily_budget_hours."""
        wm = WorkingMemory([_subject()], _prefs(hours=5.0))
        result = self.bc.check_goals(wm)
        self.assertAlmostEqual(result["daily_budget_hours"], 5.0, places=1)

    def test_recommendations_provided_when_infeasible(self):
        """Infeasible goal includes at least one actionable recommendation."""
        sub = _subject(name="Tight Subject", difficulty="hard",
                       days_ahead=1, total=5, completed=0)
        wm = WorkingMemory([sub], _prefs(hours=2.0))
        result = self.bc.check_goals(wm)
        gr = result["goal_results"][0]
        if not gr["is_feasible"]:
            self.assertGreater(len(gr["recommendations"]), 0)


# ===========================================================================
# 5. Explanation Generator Tests
# ===========================================================================

class ExplanationGeneratorTestCase(unittest.TestCase):
    """Tests for the ExplanationGenerator."""

    def setUp(self):
        self.gen = ExplanationGenerator()
        self.rule = get_rule_by_id("R02")  # emergency cram

    def test_generate_returns_required_keys(self):
        """Generated explanation has all required keys."""
        facts = SubjectFacts(_subject(days_ahead=1, completed=2, total=5), _prefs()).to_dict()
        explanation = self.gen.generate(self.rule, facts, allocated_minutes=25.0)
        for key in ["rule_id", "rule_name", "conditions_matched",
                    "action_taken", "why"]:
            self.assertIn(key, explanation)

    def test_rule_id_in_explanation(self):
        """Explanation contains the correct rule ID."""
        facts = SubjectFacts(_subject(days_ahead=1, completed=2, total=5), _prefs()).to_dict()
        expl = self.gen.generate(self.rule, facts, 30.0)
        self.assertEqual(expl["rule_id"], "R02")

    def test_conditions_matched_is_list(self):
        """conditions_matched field is a non-empty list of strings."""
        facts = SubjectFacts(_subject(), _prefs()).to_dict()
        expl = self.gen.generate(self.rule, facts, 30.0)
        self.assertIsInstance(expl["conditions_matched"], list)
        self.assertGreater(len(expl["conditions_matched"]), 0)

    def test_allocated_minutes_in_action(self):
        """action_taken contains the allocated minutes."""
        facts = SubjectFacts(_subject(days_ahead=1, completed=1, total=5), _prefs()).to_dict()
        expl = self.gen.generate(self.rule, facts, 27.0)
        self.assertEqual(expl["action_taken"]["allocated_minutes"], 27.0)

    def test_plan_summary_structure(self):
        """generate_plan_summary returns expected fields."""
        items = [
            {"priority": "CRITICAL", "allocated_minutes": 45},
            {"priority": "HIGH", "allocated_minutes": 30},
        ]
        wm_summary = {
            "plan_date": TODAY.isoformat(),
            "total_budget_minutes": 240,
            "remaining_budget_minutes": 165,
        }
        summary = self.gen.generate_plan_summary(items, wm_summary)
        self.assertIn("urgency_note", summary)
        self.assertIn("CRITICAL", summary["urgency_note"])
        self.assertEqual(summary["total_subjects_planned"], 2)

    def test_template_rendering_with_facts(self):
        """explanation template is rendered with subject name and days_remaining."""
        facts = {
            "subject_name": "Algorithms",
            "days_remaining": 2,
            "completion_pct": 40.0,
            "remaining_units": 3,
            "difficulty_level": "hard",
            "fatigue_level": "medium",
            "daily_available_hours": 4.0,
        }
        expl = self.gen.generate(self.rule, facts, 35.0)
        self.assertIn("Algorithms", expl["why"])
        self.assertIn("2", expl["why"])


# ===========================================================================
# 6. API Endpoint Tests
# ===========================================================================

class AIEndpointsTestCase(unittest.TestCase):
    """Integration tests for /api/ai/* endpoints."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    # ── /api/ai/rules ───────────────────────────────────────────────────────

    def test_list_rules_endpoint(self):
        """GET /api/ai/rules returns all rules with required fields."""
        res = self.client.get("/api/ai/rules")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreater(data["count"], 0)
        for rule in data["rules"]:
            self.assertIn("id", rule)
            self.assertIn("name", rule)
            self.assertIn("action", rule)

    # ── /api/ai/plan – empty database ──────────────────────────────────────

    def test_plan_empty_database(self):
        """POST /api/ai/plan with no subjects returns success with empty plan."""
        res = self.client.post("/api/ai/plan", json={})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["plan_items"], [])

    # ── /api/ai/plan – with subjects ───────────────────────────────────────

    def test_plan_with_sample_subjects(self):
        """POST /api/ai/plan returns plan items when subjects exist."""
        # Seed sample data
        self.client.post("/api/subjects/sample")
        res = self.client.post("/api/ai/plan", json={"save": True})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreater(len(data["plan_items"]), 0)
        self.assertIn("plan_summary", data)
        self.assertIn("explanations", data)
        # plan_id must be set when save=True
        self.assertIsNotNone(data.get("plan_id"))

    def test_plan_items_have_required_fields(self):
        """Each plan item has subject_id, priority, session_type, allocated_minutes."""
        self.client.post("/api/subjects/sample")
        res = self.client.post("/api/ai/plan", json={})
        data = res.get_json()
        for item in data.get("plan_items", []):
            self.assertIn("subject_id", item)
            self.assertIn("priority", item)
            self.assertIn("session_type", item)
            self.assertIn("allocated_minutes", item)
            self.assertIn("fired_rule_id", item)

    def test_plan_save_false_does_not_persist(self):
        """POST /api/ai/plan with save=False returns no plan_id."""
        self.client.post("/api/subjects/sample")
        res = self.client.post("/api/ai/plan", json={"save": False})
        data = res.get_json()
        self.assertIsNone(data.get("plan_id"))

    # ── /api/ai/goals ──────────────────────────────────────────────────────

    def test_goals_empty_database(self):
        """POST /api/ai/goals with no subjects returns feasible=True."""
        res = self.client.post("/api/ai/goals", json={})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["overall_feasible"])

    def test_goals_with_sample_subjects(self):
        """POST /api/ai/goals returns goal_results for each subject."""
        self.client.post("/api/subjects/sample")
        res = self.client.post("/api/ai/goals", json={})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreater(len(data["goal_results"]), 0)

    def test_goals_single_subject_filter(self):
        """POST /api/ai/goals with subject_id filters to one subject."""
        create_res = self.client.post(
            "/api/subjects",
            json={
                "name": "Isolated Subject",
                "difficulty_level": "medium",
                "syllabus_units_total": 5,
                "units_completed": 2,
                "exam_date": (TODAY + timedelta(days=10)).isoformat(),
            }
        )
        sub_id = create_res.get_json()["subject"]["id"]
        res = self.client.post("/api/ai/goals", json={"subject_id": sub_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["goal_results"]), 1)
        self.assertEqual(data["goal_results"][0]["subject_id"], sub_id)

    def test_goals_invalid_subject_id_returns_404(self):
        """POST /api/ai/goals with unknown subject_id returns 404."""
        res = self.client.post("/api/ai/goals", json={"subject_id": 99999})
        self.assertEqual(res.status_code, 404)

    def test_goals_results_have_sub_goals(self):
        """Each goal result contains sub_goals_checked."""
        self.client.post("/api/subjects/sample")
        res = self.client.post("/api/ai/goals", json={})
        data = res.get_json()
        for gr in data["goal_results"]:
            self.assertIn("sub_goals_checked", gr)
            self.assertEqual(len(gr["sub_goals_checked"]), 3)

    # ── /api/ai/explain ────────────────────────────────────────────────────

    def test_explain_plan_returns_rule_logs(self):
        """GET /api/ai/explain/<plan_id> returns logged rules."""
        self.client.post("/api/subjects/sample")
        plan_res = self.client.post("/api/ai/plan", json={"save": True})
        plan_id = plan_res.get_json()["plan_id"]

        if plan_id:
            expl_res = self.client.get(f"/api/ai/explain/{plan_id}")
            self.assertEqual(expl_res.status_code, 200)
            data = expl_res.get_json()
            self.assertTrue(data["success"])
            self.assertGreater(data["count"], 0)
            for log in data["rule_logs"]:
                self.assertIn("rule_id", log)
                self.assertIn("rule_name", log)

    def test_explain_unknown_plan_returns_404(self):
        """GET /api/ai/explain/99999 returns 404."""
        res = self.client.get("/api/ai/explain/99999")
        self.assertEqual(res.status_code, 404)


# ===========================================================================
# 7. Competing Subjects – Time Allocation Tests
# ===========================================================================

class CompetingSubjectsTestCase(unittest.TestCase):
    """
    Verify that when multiple subjects share the daily budget:
      - Forward chainer never exceeds the global daily budget.
      - Backward chainer normalised shares sum to exactly 1.0 (within float
        tolerance), ensuring no double-counting of the student's time.
    """

    def setUp(self):
        self.fc = ForwardChainer()
        self.bc = BackwardChainer()

    def _make_subjects(self, n, base_days=5, difficulty="medium"):
        """Create n distinct subjects with staggered exam dates."""
        subjects = []
        for i in range(n):
            s = _subject(
                name=f"Subject{i+1}",
                difficulty=difficulty,
                days_ahead=base_days + i,
                total=5,
                completed=1,
            )
            s["id"] = i + 1
            subjects.append(s)
        return subjects

    # ── Forward chainer budget enforcement ─────────────────────────────────

    def test_forward_budget_not_exceeded_2_subjects(self):
        """With 2 subjects, total allocated ≤ daily budget."""
        subjects = self._make_subjects(2)
        wm = WorkingMemory(subjects, _prefs(hours=2.0))  # 120-min budget
        result = self.fc.generate_plan(wm)
        total = sum(i["allocated_minutes"] for i in result["plan_items"])
        self.assertLessEqual(total, wm.total_budget_minutes + 1)

    def test_forward_budget_not_exceeded_5_subjects(self):
        """With 5 subjects, total allocated ≤ daily budget."""
        subjects = self._make_subjects(5)
        wm = WorkingMemory(subjects, _prefs(hours=4.0))  # 240-min budget
        result = self.fc.generate_plan(wm)
        total = sum(i["allocated_minutes"] for i in result["plan_items"])
        self.assertLessEqual(total, wm.total_budget_minutes + 1)

    def test_forward_budget_not_exceeded_10_subjects(self):
        """With 10 subjects and a tight budget, total allocated ≤ daily budget."""
        subjects = self._make_subjects(10)
        wm = WorkingMemory(subjects, _prefs(hours=1.5))  # 90-min budget
        result = self.fc.generate_plan(wm)
        total = sum(i["allocated_minutes"] for i in result["plan_items"])
        self.assertLessEqual(total, wm.total_budget_minutes + 1)

    # ── Backward chainer normalisation ─────────────────────────────────────

    def test_backward_shares_sum_to_1_two_subjects(self):
        """
        With 2 subjects, normalised share fractions must sum to 1.0.
        This guarantees total implied hours/day == daily_budget (no inflation).
        """
        subjects = self._make_subjects(2)
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        share_sum = sum(gr["normalised_share_fraction"]
                        for gr in result["goal_results"])
        self.assertAlmostEqual(share_sum, 1.0, places=3)

    def test_backward_shares_sum_to_1_five_subjects(self):
        """With 5 subjects, shares still sum to 1.0."""
        subjects = self._make_subjects(5)
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        share_sum = sum(gr["normalised_share_fraction"]
                        for gr in result["goal_results"])
        self.assertAlmostEqual(share_sum, 1.0, places=3)

    def test_backward_hours_per_day_sum_equals_daily_budget(self):
        """
        The sum of hours_per_day_for_subject across all subjects must equal
        the student's daily_available_hours (within float tolerance).
        This is the core correctness invariant.
        """
        subjects = self._make_subjects(4)
        daily_hours = 6.0
        wm = WorkingMemory(subjects, _prefs(hours=daily_hours))
        result = self.bc.check_goals(wm)
        total_per_day = sum(gr["hours_per_day_for_subject"]
                            for gr in result["goal_results"])
        self.assertAlmostEqual(total_per_day, daily_hours, places=2)

    def test_more_subjects_means_less_per_subject_per_day(self):
        """
        Adding subjects reduces each subject's hours_per_day (since the daily
        budget is split more ways).  A single subject gets more per day than
        when there are 5 subjects.
        """
        sub_solo = self._make_subjects(1)
        sub_crowd = self._make_subjects(5)
        prefs = _prefs(hours=4.0)

        wm1 = WorkingMemory(sub_solo, prefs)
        wm5 = WorkingMemory(sub_crowd, prefs)

        r1 = self.bc.check_goals(wm1)
        r5 = self.bc.check_goals(wm5)

        # The single subject gets all 4h; each of 5 subjects gets <4h
        h_solo = r1["goal_results"][0]["hours_per_day_for_subject"]
        # Subject1 appears in both; find the matching one in the 5-subject result
        # (same id=1)
        h_crowd = next(gr["hours_per_day_for_subject"]
                       for gr in r5["goal_results"]
                       if gr["subject_id"] == 1)
        self.assertGreater(h_solo, h_crowd)

    def test_priority_affects_share_within_budget(self):
        """
        When a forward plan marks one subject as CRITICAL and another LOW,
        the CRITICAL subject gets a larger hours_per_day_for_subject.
        Shares still sum to 1.0.
        """
        sub_crit = {**_subject(name="CritSub", days_ahead=1, completed=0, total=5), "id": 1}
        sub_low  = {**_subject(name="LowSub",  days_ahead=30, completed=4, total=5), "id": 2}

        wm = WorkingMemory([sub_crit, sub_low], _prefs(hours=4.0))

        # Fake forward plan assigning priorities
        fake_plan = [
            {"subject_id": 1, "priority": "CRITICAL"},
            {"subject_id": 2, "priority": "LOW"},
        ]
        result = self.bc.check_goals(wm, forward_plan=fake_plan)

        gr_map = {gr["subject_id"]: gr for gr in result["goal_results"]}
        h_crit = gr_map[1]["hours_per_day_for_subject"]
        h_low  = gr_map[2]["hours_per_day_for_subject"]

        self.assertGreater(h_crit, h_low,
            "CRITICAL subject should receive more hours/day than LOW subject")
        share_sum = sum(gr["normalised_share_fraction"]
                        for gr in result["goal_results"])
        self.assertAlmostEqual(share_sum, 1.0, places=3)


# ===========================================================================
# 8. Multiple Exam Dates Tests
# ===========================================================================

class MultipleExamDatesTestCase(unittest.TestCase):
    """
    Tests with subjects having different exam dates to verify:
      - Urgency ordering is correct.
      - Subjects close to exam get priority in the forward plan.
      - Backward chaining feasibility accounts for each subject's own
        days_remaining independently.
    """

    def setUp(self):
        self.fc = ForwardChainer()
        self.bc = BackwardChainer()

    def _multi_subject_set(self):
        """Return 4 subjects with staggered exam dates."""
        return [
            {"id": 1, "name": "DSA",       "difficulty_level": "hard",   "target_grade": "A",
             "exam_date": (TODAY + timedelta(days=3)).isoformat(),
             "syllabus_units_total": 6, "units_completed": 2},
            {"id": 2, "name": "OS",        "difficulty_level": "hard",   "target_grade": "A",
             "exam_date": (TODAY + timedelta(days=5)).isoformat(),
             "syllabus_units_total": 5, "units_completed": 1},
            {"id": 3, "name": "DBMS",      "difficulty_level": "medium", "target_grade": "A",
             "exam_date": (TODAY + timedelta(days=7)).isoformat(),
             "syllabus_units_total": 5, "units_completed": 3},
            {"id": 4, "name": "CN",        "difficulty_level": "medium", "target_grade": "B",
             "exam_date": (TODAY + timedelta(days=12)).isoformat(),
             "syllabus_units_total": 5, "units_completed": 4},
        ]

    def test_forward_plan_orders_by_urgency(self):
        """Subject with exam in 3 days appears before one with exam in 12 days."""
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.fc.generate_plan(wm)
        items = result["plan_items"]
        self.assertGreater(len(items), 1)
        # DSA (3 days) must come before CN (12 days)
        names = [i["subject_name"] for i in items]
        self.assertIn("DSA", names)
        self.assertIn("CN", names)
        self.assertLess(names.index("DSA"), names.index("CN"),
                        "DSA (3 days) should appear before CN (12 days)")

    def test_forward_plan_total_within_budget(self):
        """With 4 subjects and 4h budget, total minutes ≤ 240."""
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.fc.generate_plan(wm)
        total = sum(i["allocated_minutes"] for i in result["plan_items"])
        self.assertLessEqual(total, 240 + 1)  # +1 for float rounding

    def test_backward_each_subject_uses_own_days_remaining(self):
        """
        Each subject's available_study_hours uses its own days_remaining,
        not a shared value.  DSA (3 days) must have less total available
        time than CN (12 days), given equal or similar share fractions.
        """
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        gr_map = {gr["subject_name"]: gr for gr in result["goal_results"]}

        # DSA has 3 days, CN has 12 days → DSA available hours < CN available hours
        avail_dsa = gr_map["DSA"]["available_study_hours"]
        avail_cn  = gr_map["CN"]["available_study_hours"]
        self.assertLess(avail_dsa, avail_cn,
            "DSA (3 days) must have less total available hours than CN (12 days)")

    def test_backward_shares_sum_to_1_multi_exam(self):
        """With 4 subjects, normalised shares sum to 1.0."""
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        share_sum = sum(gr["normalised_share_fraction"]
                        for gr in result["goal_results"])
        self.assertAlmostEqual(share_sum, 1.0, places=3)

    def test_backward_available_hours_not_same_for_all_subjects(self):
        """
        Subjects with different exam dates must get different
        available_study_hours (even if share fractions were equal).
        This rules out the old bug where the same big number appeared
        independently for every subject.
        """
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        avail_values = [gr["available_study_hours"] for gr in result["goal_results"]]
        # Not all identical
        self.assertGreater(len(set(avail_values)), 1,
            "Subjects with different exam dates should have different available_study_hours")

    def test_backward_soonest_exam_gets_least_available_hours(self):
        """
        The subject with the fewest days remaining must have the smallest
        available_study_hours (since days × hours_per_day is smallest).
        """
        subjects = self._multi_subject_set()
        wm = WorkingMemory(subjects, _prefs(hours=4.0))
        result = self.bc.check_goals(wm)
        # Sort by days_remaining ascending; available_study_hours should follow same order
        sorted_by_days = sorted(result["goal_results"], key=lambda g: g["days_remaining"])
        avail_list = [g["available_study_hours"] for g in sorted_by_days]
        # Each should be <= the next
        for i in range(len(avail_list) - 1):
            self.assertLessEqual(
                avail_list[i], avail_list[i + 1],
                f"Subject with fewer days ({sorted_by_days[i]['subject_name']}) "
                f"should have ≤ available hours than "
                f"{sorted_by_days[i+1]['subject_name']}"
            )


if __name__ == "__main__":
    unittest.main()
