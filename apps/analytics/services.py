from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.students.models import StudentProfile
from apps.academics.models import SemesterResult
from apps.attendance.models import AttendanceRecord
from apps.lms.models import LMSActivitySummary
from apps.placements.models import PlacementAssessment
from apps.skills.models import StudentSkillAssessment
from apps.feedback.models import StudentFeedback
from apps.engagement.models import StudentEngagement
from apps.analytics.models import StudentSuccessSnapshot
from apps.interventions.models import InterventionRecord


class StudentAnalyticsEngine:
    """Transparent, rule-based student success and risk decision support.

    This is not a trained machine-learning model. Missing source data is never
    silently replaced with a benchmark score. Scores are calculated from
    observed domains only, with the weights renormalized and coverage exposed.
    """

    # Weights total 100%. Skills, engagement, and student feedback together
    # make up the 15% campus-development domain requested by the brief.
    WEIGHTS = {
        "academic": 0.30,
        "attendance": 0.25,
        "lms": 0.15,
        "placement": 0.15,
        "skills": 0.08,
        "engagement": 0.04,
        "feedback": 0.03,
    }

    @staticmethod
    def _latest_semester_result(student):
        return (
            SemesterResult.objects.filter(student=student)
            .select_related("semester__academic_year")
            .order_by(
                "-semester__academic_year__is_current",
                "-semester__academic_year__year_label",
                "-semester__number",
                "-pk",
            )
            .first()
        )

    @staticmethod
    def _attendance_percentage(student):
        """Use latest overall attendance; otherwise aggregate latest semester by classes."""
        records = AttendanceRecord.objects.filter(student=student).select_related(
            "semester__academic_year"
        )
        latest_overall = records.filter(subject__isnull=True).order_by(
            "-semester__academic_year__is_current",
            "-semester__academic_year__year_label",
            "-semester__number",
            "-last_updated",
            "-pk",
        ).first()
        if latest_overall and latest_overall.total_classes > 0:
            return round(latest_overall.attendance_percentage, 2), True

        latest = records.order_by(
            "-semester__academic_year__is_current",
            "-semester__academic_year__year_label",
            "-semester__number",
            "-last_updated",
            "-pk",
        ).first()
        if not latest:
            return None, False

        latest_semester_records = records.filter(
            semester=latest.semester,
            subject__isnull=False,
            total_classes__gt=0,
        )
        totals = list(latest_semester_records.values_list("classes_attended", "total_classes"))
        total_attended = sum(row[0] for row in totals)
        total_classes = sum(row[1] for row in totals)
        if total_classes <= 0:
            return None, False
        return round((total_attended / total_classes) * 100.0, 2), True

    @classmethod
    def calculate_student_success_score(cls, student: StudentProfile):
        """Return score, independent risk levels, data coverage and explanations."""
        now = timezone.now()
        latest_sem_result = cls._latest_semester_result(student)
        attendance_pct, attendance_available = cls._attendance_percentage(student)
        lms_summary = LMSActivitySummary.objects.filter(student=student).first()
        placement_ass = (
            PlacementAssessment.objects.filter(student=student)
            .order_by("-assessment_date", "-pk")
            .first()
        )
        skill_records = list(StudentSkillAssessment.objects.filter(student=student))
        engagement_records = list(StudentEngagement.objects.filter(student=student))
        feedback_values = list(
            StudentFeedback.objects.filter(student=student).values_list("satisfaction_score", flat=True)
        )
        feedback_count = len(feedback_values)
        feedback_score = (sum(feedback_values) / feedback_count) * 20.0 if feedback_count else None

        # Source availability is explicit; it is not inferred from model defaults.
        data_availability = {
            "academic": latest_sem_result is not None,
            "attendance": attendance_available,
            "lms": lms_summary is not None,
            "placement": placement_ass is not None,
            "skills": bool(skill_records),
            "engagement": bool(engagement_records),
            "feedback": feedback_count > 0,
        }

        component_scores = {}
        risk_flags = []
        positive_factors = []
        recommended_interventions = []
        risk_reasons = {"academic": [], "placement": [], "feedback": []}

        # 1. Academic (30%)
        cgpa = backlogs = None
        if latest_sem_result:
            cgpa = float(latest_sem_result.cgpa)
            backlogs = int(latest_sem_result.backlog_count)
            academic_score = max(0.0, min(100.0, (cgpa * 10.0) - (backlogs * 10.0)))
            component_scores["academic"] = academic_score
            if cgpa >= 8.5:
                positive_factors.append(f"Outstanding CGPA: {cgpa:.2f}")
            elif cgpa < 6.0:
                msg = f"Low CGPA: {cgpa:.2f}"
                risk_flags.append(msg)
                risk_reasons["academic"].append(msg)
            if backlogs > 0:
                msg = f"Active backlogs: {backlogs}"
                risk_flags.append(msg)
                risk_reasons["academic"].append(msg)

        # 2. Attendance (25%)
        attendance_score = None
        if attendance_available and attendance_pct is not None:
            # Keep the observed percentage continuous; thresholds are used for risk flags separately.
            attendance_score = max(0.0, min(100.0, attendance_pct))
            component_scores["attendance"] = attendance_score
            if attendance_pct >= 90:
                positive_factors.append(f"Excellent attendance: {attendance_pct:.1f}%")
            elif attendance_pct < 75:
                msg = f"Attendance below 75%: {attendance_pct:.1f}%"
                risk_flags.append(msg)
                risk_reasons["academic"].append(msg)

        # 3. LMS (15%)
        lms_score = None
        if lms_summary:
            login_score = min(100.0, (lms_summary.login_frequency / 20.0) * 100.0)
            lms_score = (
                0.40 * lms_summary.assignment_completion_pct
                + 0.30 * lms_summary.assignment_timeliness_pct
                + 0.20 * lms_summary.quiz_participation_pct
                + 0.10 * login_score
            )
            if lms_summary.last_activity_date:
                days_inactive = max(0, (now - lms_summary.last_activity_date).days)
                if days_inactive > 7:
                    lms_score = max(0.0, lms_score - min(30.0, days_inactive * 2.0))
            component_scores["lms"] = lms_score
            if lms_summary.assignment_completion_pct < 65:
                msg = f"Low LMS assignment completion: {lms_summary.assignment_completion_pct:.1f}%"
                risk_flags.append(msg)
                risk_reasons["academic"].append(msg)

        # 4. Placement readiness (15%); latest assessment only.
        placement_score = coding_score = aptitude_score = interview_score = None
        placement_risk_level = "UNKNOWN"
        if placement_ass:
            placement_score = float(placement_ass.overall_readiness_score)
            coding_score = float(placement_ass.coding_score)
            aptitude_score = float(placement_ass.aptitude_score)
            interview_score = float(placement_ass.mock_interview_score)
            component_scores["placement"] = placement_score
            if placement_score < 35:
                placement_risk_level = "CRITICAL"
            elif placement_score < 50:
                placement_risk_level = "HIGH"
            elif placement_score < 65:
                placement_risk_level = "MEDIUM"
            else:
                placement_risk_level = "LOW"
            if coding_score < 55:
                msg = f"Weak coding assessment: {coding_score:.1f}/100"
                risk_flags.append(msg)
                risk_reasons["placement"].append(msg)
            if aptitude_score < 55:
                msg = f"Aptitude assessment needs improvement: {aptitude_score:.1f}/100"
                risk_flags.append(msg)
                risk_reasons["placement"].append(msg)
            if interview_score < 55:
                msg = f"Mock interview needs improvement: {interview_score:.1f}/100"
                risk_flags.append(msg)
                risk_reasons["placement"].append(msg)

        # 5. Skills, engagement, and student feedback (15% combined).
        # Only observed records contribute; each sub-domain has its own explicit weight.
        avg_skill = (
            sum(float(record.proficiency_score) for record in skill_records) / len(skill_records)
            if skill_records else None
        )
        avg_engagement = (
            sum(float(record.engagement_score) for record in engagement_records) / len(engagement_records)
            if engagement_records else None
        )
        if avg_skill is not None:
            component_scores["skills"] = max(0.0, min(100.0, avg_skill))
        if avg_engagement is not None:
            component_scores["engagement"] = max(0.0, min(100.0, avg_engagement))
        if feedback_score is not None:
            component_scores["feedback"] = max(0.0, min(100.0, feedback_score))
            if feedback_score < 50.0:
                msg = f"Low student feedback satisfaction: {feedback_score / 20.0:.1f}/5 average"
                risk_flags.append(msg)
                risk_reasons["feedback"].append(msg)

        # Re-normalize configured weights over measured domains only.
        available_weight = sum(cls.WEIGHTS[name] for name in component_scores)
        data_coverage_pct = round(available_weight * 100.0, 1)
        if available_weight:
            overall_success_score = round(
                sum(cls.WEIGHTS[name] * score for name, score in component_scores.items()) / available_weight,
                1,
            )
            score_status = "PROVISIONAL" if data_coverage_pct < 60.0 else "CALCULATED"
        else:
            overall_success_score = None
            score_status = "INSUFFICIENT_DATA"
            risk_flags.append("Insufficient observed data to calculate a reliable success score.")

        # Academic/attendance risk is kept separate from placement risk.
        has_academic_signals = latest_sem_result is not None or attendance_available or lms_summary is not None
        if not has_academic_signals:
            academic_risk_level = "UNKNOWN"
        elif (
            (cgpa is not None and cgpa < 5.0)
            or (attendance_pct is not None and attendance_pct < 60.0)
            or (backlogs is not None and backlogs >= 3)
            or (score_status == "CALCULATED" and overall_success_score is not None and overall_success_score < 45.0)
        ):
            academic_risk_level = StudentSuccessSnapshot.RiskLevel.CRITICAL
        elif (
            (cgpa is not None and cgpa < 6.5)
            or (attendance_pct is not None and attendance_pct < 75.0)
            or (backlogs is not None and backlogs >= 1)
            or (score_status == "CALCULATED" and overall_success_score is not None and overall_success_score < 60.0)
        ):
            academic_risk_level = StudentSuccessSnapshot.RiskLevel.HIGH
        elif (
            (cgpa is not None and cgpa < 7.5)
            or (attendance_pct is not None and attendance_pct < 85.0)
            or (score_status == "CALCULATED" and overall_success_score is not None and overall_success_score < 75.0)
        ):
            academic_risk_level = StudentSuccessSnapshot.RiskLevel.MEDIUM
        else:
            academic_risk_level = StudentSuccessSnapshot.RiskLevel.LOW

        # Placement interventions are triggered independently from academic risk.
        if placement_ass and placement_risk_level in ("HIGH", "CRITICAL"):
            recommended_interventions.append(InterventionRecord.InterventionType.PLACEMENT_PREP)
        elif placement_ass and placement_risk_level == "MEDIUM" and (coding_score < 60 or aptitude_score < 60):
            recommended_interventions.append(InterventionRecord.InterventionType.PLACEMENT_PREP)
        if cgpa is not None and backlogs is not None and (cgpa < 6.5 or backlogs > 0):
            recommended_interventions.append(InterventionRecord.InterventionType.ACADEMIC_TUTORING)
        if attendance_pct is not None and attendance_pct < 75.0:
            recommended_interventions.append(InterventionRecord.InterventionType.ATTENDANCE_COUNSELING)
        if avg_skill is not None and avg_skill < 60.0:
            recommended_interventions.append(InterventionRecord.InterventionType.SKILL_BOOTCAMP)

        # Meaningful segments prioritize placement support even when academics are strong.
        if placement_risk_level in ("HIGH", "CRITICAL") and cgpa is not None and cgpa >= 7.0:
            segment = "High Academics / Placement Support Needed"
        elif academic_risk_level in ("HIGH", "CRITICAL"):
            segment = "Academic Risk"
        elif attendance_pct is not None and attendance_pct < 75.0:
            segment = "Attendance Risk"
        elif placement_risk_level in ("HIGH", "CRITICAL", "MEDIUM"):
            segment = "Placement Support Needed"
        elif lms_summary and lms_summary.assignment_completion_pct < 60.0:
            segment = "LMS Disengaged"
        elif score_status == "CALCULATED" and overall_success_score is not None and overall_success_score >= 85.0:
            segment = "High Performing"
        elif score_status != "CALCULATED":
            segment = "Insufficient Data / Review Needed"
        else:
            segment = "On Track / General Student"

        # Weighted contribution in score points makes the explanation auditable.
        score_contributions = {
            name: round((cls.WEIGHTS[name] / available_weight) * score, 2)
            for name, score in component_scores.items()
        } if available_weight else {}
        campus_domain_weight = sum(cls.WEIGHTS[name] for name in ("skills", "engagement", "feedback") if name in component_scores)
        campus_domain_score = (
            sum(cls.WEIGHTS[name] * component_scores[name] for name in ("skills", "engagement", "feedback") if name in component_scores)
            / campus_domain_weight
            if campus_domain_weight else None
        )

        explanation_json = {
            "method": "transparent_weighted_rules_v3",
            "is_machine_learning_prediction": False,
            "score_status": score_status,
            "data_coverage_percentage": data_coverage_pct,
            "available_weight": round(available_weight, 2),
            "configured_weights": cls.WEIGHTS,
            "data_availability": data_availability,
            "cgpa": cgpa,
            "backlog_count": backlogs,
            "attendance_percentage": attendance_pct,
            "lms_completion_percentage": lms_summary.assignment_completion_pct if lms_summary else None,
            "coding_score": coding_score,
            "aptitude_score": aptitude_score,
            "mock_interview_score": interview_score,
            "feedback_count": feedback_count,
            "sub_scores": {
                "academic_score": round(component_scores["academic"], 1) if "academic" in component_scores else None,
                "attendance_score": round(component_scores["attendance"], 1) if "attendance" in component_scores else None,
                "lms_score": round(component_scores["lms"], 1) if "lms" in component_scores else None,
                "placement_score": round(component_scores["placement"], 1) if "placement" in component_scores else None,
                "skills_score": round(component_scores["skills"], 1) if "skills" in component_scores else None,
                "engagement_score": round(component_scores["engagement"], 1) if "engagement" in component_scores else None,
                "feedback_score": round(component_scores["feedback"], 1) if "feedback" in component_scores else None,
                "skills_engagement_score": round(campus_domain_score, 1) if campus_domain_score is not None else None,
            },
            "score_contributions": score_contributions,
            "campus_domain_contribution": round(sum(score_contributions.get(name, 0.0) for name in ("skills", "engagement", "feedback")), 2),
            "positive_factors": positive_factors,
            "risk_flags": risk_flags,
            "academic_risk_reasons": risk_reasons["academic"],
            "placement_risk_reasons": risk_reasons["placement"],
            "feedback_risk_reasons": risk_reasons["feedback"],
            "recommended_interventions": list(dict.fromkeys(recommended_interventions)),
            "missing_domains": [name for name, available in data_availability.items() if not available],
            "interpretation": (
                "Score uses observed domains only; review data coverage before acting."
                if score_status != "CALCULATED"
                else "Score is a rule-based decision-support indicator and requires faculty review."
            ),
        }

        return {
            "overall_success_score": overall_success_score,
            "academic_risk_level": academic_risk_level,
            "placement_readiness_score": round(placement_score, 1) if placement_score is not None else None,
            "placement_risk_level": placement_risk_level,
            "segment": segment,
            "explanation_json": explanation_json,
        }

    @classmethod
    def evaluate_and_save_snapshot(cls, student: StudentProfile, auto_create_intervention=True):
        """Calculate and upsert today's snapshot; create deduplicated, risk-specific actions."""
        metrics = cls.calculate_student_success_score(student)
        snapshot, _created = StudentSuccessSnapshot.objects.update_or_create(
            student=student,
            snapshot_date=timezone.localdate(),
            defaults={
                "overall_success_score": metrics["overall_success_score"],
                "academic_risk_level": metrics["academic_risk_level"],
                "placement_readiness_score": metrics["placement_readiness_score"],
                "placement_risk_level": metrics["placement_risk_level"],
                "segment": metrics["segment"],
                "explanation_json": metrics["explanation_json"],
            },
        )

        if not auto_create_intervention:
            return snapshot

        recommended = list(metrics["explanation_json"].get("recommended_interventions", []))
        high_academic = metrics["academic_risk_level"] in (
            StudentSuccessSnapshot.RiskLevel.HIGH,
            StudentSuccessSnapshot.RiskLevel.CRITICAL,
        )
        high_placement = metrics["placement_risk_level"] in ("HIGH", "CRITICAL")
        if not (high_academic or high_placement or recommended):
            return snapshot
        if high_academic and not any(
            item in recommended
            for item in (
                InterventionRecord.InterventionType.ACADEMIC_TUTORING,
                InterventionRecord.InterventionType.ATTENDANCE_COUNSELING,
                InterventionRecord.InterventionType.SKILL_BOOTCAMP,
            )
        ):
            recommended.append(InterventionRecord.InterventionType.ACADEMIC_TUTORING)

        assigned_by = None
        try:
            assigned_by = student.department.assigned_faculty.select_related("faculty_user").first()
            assigned_by = assigned_by.faculty_user if assigned_by else None
        except AttributeError:
            assigned_by = None
        if not assigned_by:
            from django.contrib.auth import get_user_model
            assigned_by = get_user_model().objects.filter(is_superuser=True).first()
        if not assigned_by:
            return snapshot

        risk_reasons = metrics["explanation_json"].get("risk_flags", [])
        for intervention_type in recommended:
            already_active = InterventionRecord.objects.filter(
                student=student,
                intervention_type=intervention_type,
                status__in=[InterventionRecord.Status.PROPOSED, InterventionRecord.Status.IN_PROGRESS],
            ).exists()
            if already_active:
                continue
            if intervention_type == InterventionRecord.InterventionType.PLACEMENT_PREP:
                reasons = metrics["explanation_json"].get("placement_risk_reasons", [])
                reason = f"Automated Risk Flag — Placement risk ({metrics['placement_risk_level']}): " + "; ".join(reasons)
            elif intervention_type == InterventionRecord.InterventionType.SKILL_BOOTCAMP:
                reason = "Automated Risk Flag — Skill development recommended based on observed skill assessments."
            elif intervention_type == InterventionRecord.InterventionType.ATTENDANCE_COUNSELING:
                reasons = [r for r in metrics["explanation_json"].get("academic_risk_reasons", []) if "Attendance" in r]
                reason = "Automated Risk Flag — Attendance support: " + "; ".join(reasons)
            else:
                reasons = metrics["explanation_json"].get("academic_risk_reasons", [])
                reason = f"Automated Risk Flag — Academic risk ({metrics['academic_risk_level']}): " + "; ".join(reasons)
            InterventionRecord.objects.create(
                student=student,
                assigned_by=assigned_by,
                assigned_to=assigned_by,
                intervention_type=intervention_type,
                reason=reason,
                status=InterventionRecord.Status.PROPOSED,
                follow_up_date=timezone.localdate() + timedelta(days=14),
            )
        return snapshot

    @classmethod
    def evaluate_all_students(cls):
        """Evaluate and update snapshots for all active students."""
        active_students = StudentProfile.objects.filter(
            enrollment_status=StudentProfile.EnrollmentStatus.ACTIVE
        )
        updated = 0
        with transaction.atomic():
            for student in active_students.iterator():
                cls.evaluate_and_save_snapshot(student)
                updated += 1
        return updated
