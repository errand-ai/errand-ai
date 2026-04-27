## MODIFIED Requirements

### Requirement: TwitterPlatform class
The system SHALL provide a `TwitterPlatform` class in `backend/platforms/twitter.py` that extends the `Platform` base class. The class SHALL declare capabilities `{POST, MEDIA, ANALYTICS, SEARCH}`. The `verify_credentials()` method SHALL make a test API call (e.g., `client.get_me()`) to validate the credentials. The `post()` method SHALL create a tweet via the Tweepy `Client`.

#### Scenario: TwitterPlatform info
- **WHEN** `TwitterPlatform.info()` is called
- **THEN** it returns `PlatformInfo` with `id="twitter"`, `label="Twitter/X"`, capabilities `{POST, MEDIA, ANALYTICS, SEARCH}`, and credential_schema defining `api_key`, `api_secret`, `access_token`, `access_secret`

#### Scenario: Verify valid credentials
- **WHEN** `verify_credentials()` is called with valid Twitter API credentials
- **THEN** it returns `True`

#### Scenario: Verify invalid credentials
- **WHEN** `verify_credentials()` is called with invalid credentials
- **THEN** it returns `False`
