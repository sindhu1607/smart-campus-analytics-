# Scoring Engine v2 — Changes

## Files changed

- `apps/analytics/services.py`: observed-data-only scoring, renormalized weights, weighted data coverage, score status, per-domain sub-scores and score contributions, latest semester/placement assessment selection, separate placement risk and risk reasons, placement-specific interventions, and deduplication by intervention type.
- `apps/analytics/models.py`: added `UNKNOWN` academic risk and made it the default for new snapshots.
- `apps/analytics/migrations/0003_unknown_academic_risk.py`: migration for the new risk choice/default.
- `apps/analytics/views.py`: placement readiness no longer invents benchmark values for unassessed students; risk API includes placement risk, score status, coverage and explanations; summary average only includes fully calculated scores.
- `apps/analytics/dashboard_views.py`: average success score excludes insufficient/provisional records; reports calculated-score count and unknown-risk count.
- `templates/dashboards/overview_dashboard.html`: shows calculated-score count and includes insufficient-data risk in the filter/chart.
- `apps/analytics/tests.py`: tests for no-data handling, observed-domain scoring, independent placement risk and latest placement assessment selection.
- `docs/STUDENT_SUCCESS_SCORE_METHODOLOGY.md`: documents missing-data policy and clarifies that the current engine is rule-based, not a trained ML model.

## Score interpretation

- `CALCULATED`: weighted data coverage is at least 60%.
- `PROVISIONAL`: some measured domains exist, but coverage is below 60%.
- `INSUFFICIENT_DATA`: no scored domain has observed data. The numeric `0.0` is retained only for schema compatibility; the profile is flagged `UNKNOWN` and must not be interpreted as a failing student.

The composite score is computed over available scored domains only; configured weights are renormalized. Coverage is separately calculated from observed sources, including partial skills/engagement availability.

## Important limitation

The engine is transparent, rule-based decision support. It is not a trained machine-learning prediction model. Faculty review remains required before interventions are acted upon.


## Final hardening pass

- Added student feedback satisfaction to the 15% campus-development component (skills 8%, engagement 4%, feedback 3%).
- Removed the discontinuous attendance-score penalty; raw observed attendance contributes continuously while policy thresholds still drive risk flags.
- Scores are stored as null when no measured domain exists; placement readiness is null when no placement assessment exists.
- Updated student detail, directory, and segmentation templates to show N/A/missing-data labels instead of invented numeric fallback values.
- Added a migration to make score fields nullable and clean legacy snapshots clearly marked as unassessed.
- CI now runs app-level analytics tests as well as the integration test package.
- Intervention reasons now distinguish academic, placement, attendance, and skill-development actions.
