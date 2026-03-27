# Ksense Healthcare API Assessment

Solution for the Ksense Healthcare API assessment.

## What it does

- Fetches patient data from the assessment API
- Handles pagination
- Retries on rate limits and intermittent server failures
- Scores patient risk from:
  - blood pressure
  - temperature
  - age
- Identifies:
  - high-risk patients
  - fever patients
  - data quality issues

## Implementation

Main file: `healthcare_assessment.py`

## Notes

The script includes:
- retry handling for `429`, `500`, and `503`
- validation for malformed or missing blood pressure, temperature, and age values
- a dry-run default mode to avoid accidental re-submission
- optional `--submit` mode for posting results to the API
