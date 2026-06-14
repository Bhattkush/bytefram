# Database Notes

Backend persistence uses Firebase Firestore.

Collections used by the API:

1. `users`
2. `farmer_profiles`
3. `predictions_history`
4. `weather_cache`

Required backend environment variables:

- `FIREBASE_PROJECT_ID`
- `FIREBASE_CREDENTIALS_PATH` (service account JSON path) or `FIREBASE_CREDENTIALS_JSON`

Firestore is schemaless, so no SQL migration step is required.
