- `AGENT_RESOURCE_ID_INVALID`: an ID is not in the backend allowlist; reject the candidate.
- `WEATHER_NOT_SUPPORTED`: propose an indoor or weather-compatible alternative.
- `AGE_NOT_SUPPORTED`: do not recommend the activity for the given child age.
- `FORMAT_ERROR`: return a schema-valid JSON candidate after repair; the backend still validates all IDs and numbers.

