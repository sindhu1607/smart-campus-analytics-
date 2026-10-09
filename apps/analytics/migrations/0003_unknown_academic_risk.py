from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analytics", "0002_placement_risk_level")]

    operations = [
        migrations.AlterField(
            model_name="studentsuccesssnapshot",
            name="academic_risk_level",
            field=models.CharField(
                choices=[
                    ("UNKNOWN", "Insufficient Data"),
                    ("LOW", "Low Risk"),
                    ("MEDIUM", "Medium Risk"),
                    ("HIGH", "High Risk"),
                    ("CRITICAL", "Critical Risk"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
    ]
