# Student Success Score & Risk Methodology

## Purpose

The platform combines available student indicators into a transparent 0–100 decision-support score and separately classifies academic/attendance risk and placement readiness risk. It is a **rule-based scoring system, not a trained machine-learning model or a probability of failure**. Faculty must review the underlying evidence before taking action.

## Scoring weights

| Domain | Weight | Inputs / calculation |
|---|---:|---|
| Academic | 30% | `CGPA × 10 − backlog_count × 10`, clamped to 0–100 |
| Attendance | 25% | Latest overall attendance percentage; if absent, weighted aggregation of subject records for the latest semester |
| LMS | 15% | 40% assignment completion + 30% timeliness + 20% quiz participation + 10% normalized monthly logins; recent inactivity may reduce the score |
| Placement readiness | 15% | Mean of aptitude, coding, mock interview, resume readiness, and communication scores in the latest assessment |
| Skills | 8% | Mean of observed skill-assessment scores |
| Engagement | 4% | Mean of observed extracurricular/activity engagement scores |
| Student feedback | 3% | Mean satisfaction rating on a 1–5 scale, multiplied by 20 |
| **Total** | **100%** | Skills, engagement and feedback together make up 15% |

The score is a weighted mean of the domains with observed records only. Configured weights are renormalized over observed domains, and the result includes per-domain weighted contributions so the calculation can be audited. Attendance is used continuously as observed; risk thresholds are separate from the score formula.

## Data completeness

- `CALCULATED`: at least 60% of configured weight has observed source data.
- `PROVISIONAL`: some observed data exists, but coverage is below 60%; the score is displayed with a warning and should not be used as a firm classification.
- `INSUFFICIENT_DATA`: no scored domain has an observed record. The score is stored as `null`, not zero, to avoid presenting missing information as poor performance.
- Missing domains are listed in `explanation_json.missing_domains`; sub-scores and weighted contributions are `null`/absent when the underlying data is missing.

## Risk rules

### Academic / attendance risk

- **CRITICAL:** CGPA below 5.0, attendance below 60%, at least 3 backlogs, or a fully calculated score below 45.
- **HIGH:** CGPA below 6.5, attendance below 75%, at least 1 backlog, or a fully calculated score below 60.
- **MEDIUM:** CGPA below 7.5, attendance below 85%, or a fully calculated score below 75.
- **LOW:** available academic signals do not meet a higher-risk rule.
- **UNKNOWN:** no academic, attendance, or LMS signals are available.

A provisional composite score does not by itself raise academic risk. Direct observed indicators such as CGPA, backlogs and attendance can still raise risk.

### Placement risk (independent of academic risk)

- **CRITICAL:** readiness below 35.
- **HIGH:** readiness below 50.
- **MEDIUM:** readiness below 65.
- **LOW:** readiness at least 65.
- **UNKNOWN:** no placement assessment is recorded.

This independent classification is intended to identify students with strong academics but weak coding, aptitude, interview, resume, or communication readiness.

## Explainability and interventions

Each snapshot records the method version, score status, data coverage, source availability, sub-scores, weighted contributions, positive factors, risk flags, separate academic/placement/feedback reasons, segment, and recommended intervention types. Duplicate active interventions of the same type are not created. The application is a support tool; it should not automatically penalize a student or replace human review.

## Limitations

1. The current engine is deterministic and rule-based. Do not describe it as a trained ML model or calibrated prediction probability.
2. Thresholds and weights are prototype assumptions and should be reviewed with institutional stakeholders before use with real student data.
3. Demo data must be synthetic. Import real student records only with institutional approval and suitable access controls.
