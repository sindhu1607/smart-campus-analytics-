from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.students.models import StudentProfile

class StudentSuccessSnapshot(models.Model):
    class RiskLevel(models.TextChoices):
        UNKNOWN = 'UNKNOWN', 'Insufficient Data'
        LOW = 'LOW', 'Low Risk'
        MEDIUM = 'MEDIUM', 'Medium Risk'
        HIGH = 'HIGH', 'High Risk'
        CRITICAL = 'CRITICAL', 'Critical Risk'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='success_snapshots')
    snapshot_date = models.DateField(auto_now_add=True)
    overall_success_score = models.FloatField(
        null=True,
        blank=True,
        default=None,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Calculated Explainable Student Success Score (0-100); null when source data is insufficient"
    )
    academic_risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.UNKNOWN
    )
    placement_readiness_score = models.FloatField(
        null=True,
        blank=True,
        default=None,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    placement_risk_level = models.CharField(
        max_length=20,
        choices=[
            ("UNKNOWN", "Not Assessed"),
            ("LOW", "Low Placement Risk"),
            ("MEDIUM", "Medium Placement Risk"),
            ("HIGH", "High Placement Risk"),
            ("CRITICAL", "Critical Placement Risk"),
        ],
        default="UNKNOWN",
    )
    segment = models.CharField(
        max_length=100,
        default="General Student",
        help_text="e.g., High Performer, Academic Risk, Attendance Risk, Placement Prepared"
    )
    explanation_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable breakdown of factors contributing to success score and risk assessment"
    )

    class Meta:
        ordering = ['-snapshot_date', '-overall_success_score']

    def __str__(self):
        return f"{self.student.student_id} - Score: {self.overall_success_score} ({self.get_academic_risk_level_display()})"
