## Purpose

Email platform integration providing IMAP/SMTP connectivity, credential verification, and platform registration for errand's dedicated mailbox.

## ADDED Requirements

### Requirement: Email platform class

The system SHALL provide an `EmailPlatform` class in `errand/platforms/email.py` that extends the `Platform` base class. The class SHALL implement `info()` and `verify_credentials()`. The platform SHALL declare `PlatformCapability.EMAIL` in its capabilities.

#### Scenario: Email platform info

- **WHEN** `EmailPlatform().info()` is called
- **THEN** the returned `PlatformInfo` has `id="email"`, `label="Email"`, capabilities containing `PlatformCapability.EMAIL`, and a `credential_schema` with fields for IMAP/SMTP connection, authentication, task profile, poll interval, and authorised recipients

### Requirement: Email credential schema

The `EmailPlatform` credential schema SHALL include: `imap_host` (text, required), `imap_port` (text, required), `smtp_host` (text, required), `smtp_port` (text, required), `security` (select with SSL/TLS and STARTTLS options, required), `username` (text, required), `password` (password, required), `email_profile` (profile_select, required), `poll_interval` (text, optional, help text indicating 60s minimum), and `authorized_recipients` (textarea, optional, help text indicating one email per line).

#### Scenario: Credential schema structure

- **WHEN** `EmailPlatform().info().credential_schema` is inspected
- **THEN** it contains 10 fields covering IMAP/SMTP connection, authentication, and email-specific settings

### Requirement: Email IMAP credential verification

The `verify_credentials()` method SHALL connect to the IMAP server using the provided host, port, username, password, and security mode. It SHALL use SSL/TLS for direct encrypted connections or STARTTLS for upgrade-based connections. It SHALL attempt to SELECT the INBOX folder. It SHALL return `True` if the connection and login succeed. It SHALL return `False` for any connection, authentication, or protocol error.

#### Scenario: Verify valid IMAP credentials

- **WHEN** `verify_credentials()` is called with valid IMAP connection details
- **THEN** the method connects, logs in, selects INBOX, and returns `True`

#### Scenario: Verify invalid IMAP credentials

- **WHEN** `verify_credentials()` is called with incorrect username or password
- **THEN** the method returns `False`

#### Scenario: Verify unreachable IMAP server

- **WHEN** `verify_credentials()` is called with a host that does not respond
- **THEN** the method returns `False`

### Requirement: Email SMTP credential verification

The `verify_credentials()` method SHALL also verify SMTP connectivity by connecting to the SMTP server using the provided host, port, and security mode, and authenticating with the username and password. Verification SHALL fail if either IMAP or SMTP connectivity fails.

#### Scenario: Verify valid SMTP credentials

- **WHEN** `verify_credentials()` is called with valid IMAP and SMTP connection details
- **THEN** both connections succeed and the method returns `True`

#### Scenario: IMAP valid but SMTP fails

- **WHEN** `verify_credentials()` is called with valid IMAP but invalid SMTP details
- **THEN** the method returns `False`

### Requirement: Email platform registration

The backend SHALL register `EmailPlatform` in the platform registry during application startup, alongside existing platforms.

#### Scenario: Email appears in platform list

- **WHEN** the application has started and an authenticated user requests `GET /api/platforms`
- **THEN** the response includes a platform with `id="email"` and `label="Email"`
