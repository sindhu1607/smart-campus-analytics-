import csv
import tempfile
from pathlib import Path

from django.test import TestCase

from apps.analytics.models import StudentSuccessSnapshot
from apps.attendance.models import AttendanceRecord
from apps.lms.models import LMSActivitySummary
from apps.placements.models import PlacementAssessment
from apps.students.models import StudentProfile
from apps.skills.models import StudentSkillAssessment
from apps.engagement.models import StudentEngagement
from apps.feedback.models import StudentFeedback
from apps.students.services import DataImportService
from apps.academics.models import SemesterResult


class DataImportServiceTests(TestCase):
    def _csv_file(self, rows, columns):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", newline="", encoding="utf-8", delete=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        handle.close()
        return handle.name

    def test_missing_domains_are_not_fabricated_during_import(self):
        path = self._csv_file(
            [{"student_id": "IMPORT001", "name": "Test Student"}],
            ["student_id", "name"],
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 1)
        student = StudentProfile.objects.get(student_id="IMPORT001")
        self.assertFalse(SemesterResult.objects.filter(student=student).exists())
        self.assertFalse(AttendanceRecord.objects.filter(student=student).exists())
        self.assertFalse(LMSActivitySummary.objects.filter(student=student).exists())
        self.assertFalse(PlacementAssessment.objects.filter(student=student).exists())
        snapshot = StudentSuccessSnapshot.objects.filter(student=student).first()
        self.assertIsNone(snapshot)

    def test_invalid_numeric_row_is_skipped_with_validation_error(self):
        path = self._csv_file(
            [{"student_id": "IMPORT002", "name": "Bad CGPA", "cgpa": "not-a-number"}],
            ["student_id", "name", "cgpa"],
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 0)
        self.assertTrue(any("cgpa" in error for error in result["errors"]))
        self.assertFalse(StudentProfile.objects.filter(student_id="IMPORT002").exists())

    def test_partial_placement_columns_do_not_create_fabricated_scores(self):
        path = self._csv_file(
            [{
                "student_id": "IMPORT003", "name": "Placement Student", "aptitude_score": "80",
                "coding_score": "70", "mock_interview_score": "75",
            }],
            ["student_id", "name", "aptitude_score", "coding_score", "mock_interview_score"],
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 1)
        self.assertFalse(PlacementAssessment.objects.filter(student__student_id="IMPORT003").exists())
        self.assertTrue(any("placement assessment" in warning.lower() for warning in result["warnings"]))

    def test_complete_placement_columns_import_all_components(self):
        columns = [
            "student_id", "name", "aptitude_score", "coding_score", "mock_interview_score",
            "resume_readiness_score", "communication_score",
        ]
        path = self._csv_file(
            [{
                "student_id": "IMPORT005", "name": "Complete Placement Student", "aptitude_score": "80",
                "coding_score": "70", "mock_interview_score": "75", "resume_readiness_score": "78",
                "communication_score": "82",
            }],
            columns,
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 1)
        assessment = PlacementAssessment.objects.get(student__student_id="IMPORT005")
        self.assertEqual(assessment.resume_readiness_score, 78.0)
        self.assertEqual(assessment.communication_score, 82.0)
        self.assertGreater(assessment.overall_readiness_score, 0)

    def test_partial_lms_columns_do_not_create_defaulted_activity(self):
        path = self._csv_file(
            [{"student_id": "IMPORT006", "name": "Partial LMS", "lms_login_frequency": "12"}],
            ["student_id", "name", "lms_login_frequency"],
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 1)
        self.assertFalse(LMSActivitySummary.objects.filter(student__student_id="IMPORT006").exists())
        self.assertTrue(any("LMS activity" in warning for warning in result["warnings"]))

    def test_complete_lms_columns_import_without_fake_last_activity(self):
        path = self._csv_file(
            [{
                "student_id": "IMPORT007", "name": "Complete LMS", "lms_login_frequency": "12",
                "assignment_completion_percentage": "80", "assignment_timeliness_percentage": "70",
                "quiz_participation_percentage": "90", "learning_resource_views": "22",
            }],
            ["student_id", "name", "lms_login_frequency", "assignment_completion_percentage",
             "assignment_timeliness_percentage", "quiz_participation_percentage", "learning_resource_views"],
        )
        result = DataImportService.import_from_file(path)

        self.assertEqual(result["imported_count"], 1)
        summary = LMSActivitySummary.objects.get(student__student_id="IMPORT007")
        self.assertEqual(summary.assignment_timeliness_pct, 70.0)
        self.assertEqual(summary.quiz_participation_pct, 90.0)
        self.assertEqual(summary.learning_resource_views, 22)
        self.assertIsNone(summary.last_activity_date)

    def test_import_populates_optional_engagement_skills_and_feedback_domains(self):
        path = self._csv_file(
            [{
                "student_id": "IMPORT004", "name": "All Domains", "engagement_score": "82",
                "technical_skill_score": "78", "soft_skill_score": "85", "feedback_score": "4",
            }],
            ["student_id", "name", "engagement_score", "technical_skill_score", "soft_skill_score", "feedback_score"],
        )
        result = DataImportService.import_from_file(path)
        self.assertEqual(result["imported_count"], 1)
        student = StudentProfile.objects.get(student_id="IMPORT004")
        self.assertTrue(StudentEngagement.objects.filter(student=student, engagement_score=82).exists())
        self.assertEqual(StudentSkillAssessment.objects.filter(student=student).count(), 2)
        self.assertTrue(StudentFeedback.objects.filter(student=student, satisfaction_score=4).exists())

