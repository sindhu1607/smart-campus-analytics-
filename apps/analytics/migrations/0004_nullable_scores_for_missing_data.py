from django.db import migrations, models
import django.core.validators


def clear_unassessed_legacy_scores(apps, schema_editor):
    Snapshot = apps.get_model("analytics", "StudentSuccessSnapshot")
    for snapshot in Snapshot.objects.all().iterator():
        explanation = snapshot.explanation_json or {}
        changed = []
        if explanation.get("method") != "transparent_weighted_rules_v3":
            # Legacy values were calculated with the previous formula or may be placeholders.
            # Clear them so the dashboard cannot imply they were computed by the current method.
            snapshot.overall_success_score = None
            changed.append("overall_success_score")
        if snapshot.placement_risk_level == "UNKNOWN":
            snapshot.placement_readiness_score = None
            changed.append("placement_readiness_score")
        if changed:
            snapshot.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("analytics", "0003_unknown_academic_risk")]

    operations = [
        migrations.AlterField(
            model_name="studentsuccesssnapshot",
            name="overall_success_score",
            field=models.FloatField(
                blank=True,
                default=None,
                help_text="Calculated Explainable Student Success Score (0-100); null when source data is insufficient",
                null=True,
                validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(100.0)],
            ),
        ),
        migrations.AlterField(
            model_name="studentsuccesssnapshot",
            name="placement_readiness_score",
            field=models.FloatField(
                blank=True,
                default=None,
                null=True,
                validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(100.0)],
            ),
        ),
        migrations.RunPython(clear_unassessed_legacy_scores, migrations.RunPython.noop),
    ]
