from django.test import TestCase

from apps.students.models import Department, Program, AcademicYear, Semester, StudentProfile
from apps.academics.models import SemesterResult
from apps.attendance.models import AttendanceRecord
from apps.placements.models import PlacementAssessment
from apps.feedback.models import FeedbackCategory, StudentFeedback
from apps.analytics.services import StudentAnalyticsEngine


class StudentAnalyticsEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="CSE", name="Computer Science")
        cls.program = Program.objects.create(
            code="BTECH-CSE", name="B.Tech CSE", department=cls.department
        )
        cls.year = AcademicYear.objects.create(year_label="2026-2027", is_current=True)
        cls.semester = Semester.objects.create(number=5, academic_year=cls.year, is_active=True)
        cls.student = StudentProfile.objects.create(
            student_id="TEST001", first_name="Test", last_name="Student",
            email="test001@example.edu", department=cls.department, program=cls.program,
            current_semester=5, admission_year=2024,
        )

    def test_no_source_data_is_not_filled_with_benchmark_defaults(self):
        metrics = StudentAnalyticsEngine.calculate_student_success_score(self.student)
        explanation = metrics["explanation_json"]

        self.assertEqual(metrics["academic_risk_level"], "UNKNOWN")
        self.assertEqual(metrics["placement_risk_level"], "UNKNOWN")
        self.assertEqual(explanation["score_status"], "INSUFFICIENT_DATA")
        self.assertEqual(explanation["data_coverage_percentage"], 0.0)
        self.assertIsNone(metrics["overall_success_score"])
        self.assertIsNone(metrics["placement_readiness_score"])
        self.assertEqual(metrics["segment"], "Insufficient Data / Review Needed")
        self.assertIsNone(explanation["sub_scores"]["academic_score"])
        self.assertIsNone(explanation["sub_scores"]["placement_score"])
        self.assertIn("academic", explanation["missing_domains"])

    def test_score_uses_observed_domains_and_reports_coverage(self):
        SemesterResult.objects.create(
            student=self.student, semester=self.semester, sgpa=8.0, cgpa=8.0,
            credits_completed=20, backlog_count=0, passed=True,
        )
        AttendanceRecord.objects.create(
            student=self.student, semester=self.semester, subject=None,
            total_classes=100, classes_attended=90,
        )

        metrics = StudentAnalyticsEngine.calculate_student_success_score(self.student)
        explanation = metrics["explanation_json"]

        self.assertEqual(metrics["overall_success_score"], 84.5)
        self.assertEqual(explanation["score_status"], "PROVISIONAL")
        self.assertEqual(explanation["data_coverage_percentage"], 55.0)
        self.assertIsNone(explanation["sub_scores"]["lms_score"])
        self.assertIsNone(explanation["sub_scores"]["placement_score"])
        self.assertIn("score_contributions", explanation)

    def test_strong_academics_can_have_independent_high_placement_risk(self):
        SemesterResult.objects.create(
            student=self.student, semester=self.semester, sgpa=9.0, cgpa=9.0,
            credits_completed=20, backlog_count=0, passed=True,
        )
        AttendanceRecord.objects.create(
            student=self.student, semester=self.semester, subject=None,
            total_classes=100, classes_attended=95,
        )
        PlacementAssessment.objects.create(
            student=self.student, aptitude_score=35, coding_score=30,
            mock_interview_score=40, resume_readiness_score=50, communication_score=45,
        )

        metrics = StudentAnalyticsEngine.calculate_student_success_score(self.student)
        explanation = metrics["explanation_json"]

        self.assertEqual(metrics["placement_risk_level"], "HIGH")
        self.assertIn("High Academics / Placement Support Needed", metrics["segment"])
        self.assertIn("PLACEMENT_PREP", explanation["recommended_interventions"])
        self.assertTrue(explanation["placement_risk_reasons"])


    def test_feedback_is_normalized_and_included_in_explainable_score(self):
        category = FeedbackCategory.objects.create(name="Course Experience")
        StudentFeedback.objects.create(
            student=self.student, category=category, satisfaction_score=4,
            comments="Helpful course", is_confidential=True,
        )
        metrics = StudentAnalyticsEngine.calculate_student_success_score(self.student)
        explanation = metrics["explanation_json"]
        self.assertEqual(explanation["sub_scores"]["feedback_score"], 80.0)
        self.assertEqual(explanation["data_coverage_percentage"], 3.0)
        self.assertEqual(explanation["score_status"], "PROVISIONAL")
        self.assertIn("feedback", explanation["data_availability"])

    def test_latest_placement_assessment_is_used(self):
        from datetime import date, timedelta
        older = PlacementAssessment.objects.create(
            student=self.student, aptitude_score=90, coding_score=90, mock_interview_score=90,
            resume_readiness_score=90, communication_score=90,
        )
        latest = PlacementAssessment.objects.create(
            student=self.student, aptitude_score=30, coding_score=30,
            mock_interview_score=30, resume_readiness_score=30, communication_score=30,
        )
        PlacementAssessment.objects.filter(pk=older.pk).update(assessment_date=date.today() - timedelta(days=30))
        PlacementAssessment.objects.filter(pk=latest.pk).update(assessment_date=date.today())

        metrics = StudentAnalyticsEngine.calculate_student_success_score(self.student)
        self.assertEqual(metrics["placement_readiness_score"], 30.0)
        self.assertEqual(metrics["placement_risk_level"], "CRITICAL")
