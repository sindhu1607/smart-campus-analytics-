from django.core.management.base import BaseCommand
from apps.analytics.services import StudentAnalyticsEngine

class Command(BaseCommand):
    help = 'Calculates explainable student success scores, independent risk levels, and recommended interventions.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Running the explainable analytics engine for all active students..."))
        count = StudentAnalyticsEngine.evaluate_all_students()
        self.stdout.write(self.style.SUCCESS(f"Successfully calculated explainable success scores and updated snapshots for {count} students!"))
