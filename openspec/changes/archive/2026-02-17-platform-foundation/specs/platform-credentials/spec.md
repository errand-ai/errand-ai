## ADDED Requirements

### Requirement: PlatformCredential database model
The system SHALL define a `PlatformCredential` SQLAlchemy model in `backend/models.py` with columns: `platform_id` (Text, primary key), `encrypted_data` (Text, not null — Fernet ciphertext), `status` (Text, not null, default "disconnected"), `last_verified_at` (DateTime with timezone, nullable), and `updated_at` (DateTime with timezone, not null, auto-updated).

#### Scenario: Model creates correct table
- **WHEN** the Alembic migration runs
- **THEN** a `platform_credentials` table is created with the specified columns

#### Scenario: Migration is reversible
- **WHEN** the Alembic migration is downgraded
- **THEN** the `platform_credentials` table is dropped

### Requirement: Fernet encryption service
The system SHALL provide a credential encryption module in `backend/platforms/credentials.py` that uses `cryptography.fernet.Fernet` for encrypting and decrypting credential dicts. The module SHALL read the encryption key from the `CREDENTIAL_ENCRYPTION_KEY` environment variable. The `encrypt(data: dict) -> str` function SHALL JSON-serialize the dict and encrypt it, returning the ciphertext as a string. The `decrypt(ciphertext: str) -> dict` function SHALL decrypt and JSON-deserialize, returning the original dict.

#### Scenario: Encrypt and decrypt round-trip
- **WHEN** `encrypt({"api_key": "abc123"})` is called and the result is passed to `decrypt()`
- **THEN** the original dict `{"api_key": "abc123"}` is returned

#### Scenario: Decrypt with wrong key fails
- **WHEN** data encrypted with key A is decrypted with key B
- **THEN** an `InvalidToken` exception is raised

#### Scenario: Missing encryption key
- **WHEN** `CREDENTIAL_ENCRYPTION_KEY` is not set and encryption is attempted
- **THEN** a clear error is raised indicating the encryption key is not configured

### Requirement: Save platform credentials API
The backend SHALL expose `PUT /api/platforms/{platform_id}/credentials` requiring the `admin` role. The endpoint SHALL accept a JSON object containing the credential fields for the platform. The endpoint SHALL validate that the platform_id corresponds to a registered platform. The endpoint SHALL call the platform's `verify_credentials()` method to test the credentials. If verification succeeds, the endpoint SHALL encrypt the credentials, store them in the `PlatformCredential` table (upsert), set status to "connected" and `last_verified_at` to now. If verification fails, the endpoint SHALL return HTTP 400 with an error message. The endpoint SHALL return the platform status (never the raw credentials).

#### Scenario: Save valid credentials
- **WHEN** an admin sends `PUT /api/platforms/twitter/credentials` with valid Twitter API credentials
- **THEN** the credentials are encrypted, stored, verified, and the response is `{"platform_id": "twitter", "status": "connected", "last_verified_at": "..."}`

#### Scenario: Save invalid credentials
- **WHEN** an admin sends `PUT /api/platforms/twitter/credentials` with invalid credentials that fail verification
- **THEN** the response is HTTP 400 with `{"detail": "Credential verification failed: <reason>"}`

#### Scenario: Unknown platform
- **WHEN** an admin sends `PUT /api/platforms/unknown/credentials`
- **THEN** the response is HTTP 404 with `{"detail": "Platform 'unknown' not found"}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user sends `PUT /api/platforms/twitter/credentials`
- **THEN** the response is HTTP 403

### Requirement: Get platform credentials status API
The backend SHALL expose `GET /api/platforms/{platform_id}/credentials` requiring the `admin` role. The endpoint SHALL return the credential status (connected/disconnected/error), last_verified_at, and the credential field names that are configured (but never the actual values). If no credentials are stored, it SHALL return status "disconnected".

#### Scenario: Credentials configured
- **WHEN** an admin requests `GET /api/platforms/twitter/credentials` and Twitter credentials exist
- **THEN** the response includes `{"platform_id": "twitter", "status": "connected", "last_verified_at": "...", "configured_fields": ["api_key", "api_secret", "access_token", "access_secret"]}`

#### Scenario: No credentials configured
- **WHEN** an admin requests `GET /api/platforms/twitter/credentials` and no Twitter credentials exist
- **THEN** the response is `{"platform_id": "twitter", "status": "disconnected", "last_verified_at": null, "configured_fields": []}`

### Requirement: Delete platform credentials API
The backend SHALL expose `DELETE /api/platforms/{platform_id}/credentials` requiring the `admin` role. The endpoint SHALL remove the encrypted credentials from the database and set the status to "disconnected". The endpoint SHALL return HTTP 204 on success.

#### Scenario: Delete existing credentials
- **WHEN** an admin sends `DELETE /api/platforms/twitter/credentials` and credentials exist
- **THEN** the credentials are removed from the database and HTTP 204 is returned

#### Scenario: Delete non-existent credentials
- **WHEN** an admin sends `DELETE /api/platforms/twitter/credentials` and no credentials exist
- **THEN** HTTP 204 is returned (idempotent)

### Requirement: Verify platform credentials API
The backend SHALL expose `POST /api/platforms/{platform_id}/credentials/verify` requiring the `admin` role. The endpoint SHALL decrypt the stored credentials and call the platform's `verify_credentials()` method. The endpoint SHALL update the status and `last_verified_at` based on the result. This allows re-verifying existing credentials without re-entering them.

#### Scenario: Re-verify valid credentials
- **WHEN** an admin sends `POST /api/platforms/twitter/credentials/verify` and the stored credentials are valid
- **THEN** the status is updated to "connected", `last_verified_at` is updated, and the response reflects this

#### Scenario: Re-verify expired credentials
- **WHEN** an admin sends `POST /api/platforms/twitter/credentials/verify` and the credentials have been revoked
- **THEN** the status is updated to "error" and the response includes the error reason

#### Scenario: No credentials to verify
- **WHEN** an admin sends `POST /api/platforms/twitter/credentials/verify` and no credentials are stored
- **THEN** the response is HTTP 400 with `{"detail": "No credentials configured for platform 'twitter'"}`

### Requirement: Load credentials helper
The credential module SHALL provide an async function `load_credentials(platform_id: str, session: AsyncSession) -> dict | None` that loads and decrypts credentials from the database. This function is used by platform implementations to access credentials at runtime. It SHALL return `None` if no credentials are stored.

#### Scenario: Load existing credentials
- **WHEN** `load_credentials("twitter", session)` is called and Twitter credentials exist
- **THEN** the decrypted credential dict is returned

#### Scenario: Load non-existent credentials
- **WHEN** `load_credentials("slack", session)` is called and no Slack credentials exist
- **THEN** `None` is returned
