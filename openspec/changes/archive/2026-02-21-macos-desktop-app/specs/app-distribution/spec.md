## ADDED Requirements

### Requirement: Code signing with Developer ID
The app SHALL be signed with an Apple Developer ID certificate for distribution outside the Mac App Store. The app SHALL use hardened runtime. The signing SHALL be automated in the app's CI/CD pipeline.

#### Scenario: App signed for distribution
- **WHEN** the app is built for release
- **THEN** the binary is signed with a Developer ID certificate and hardened runtime is enabled

### Requirement: Notarization
The app SHALL be submitted to Apple's notarization service before distribution. The notarization ticket SHALL be stapled to the app. Users SHALL see "verified developer" in Gatekeeper when opening the app.

#### Scenario: App notarized
- **WHEN** the app is built and signed
- **THEN** it is submitted to `notarytool` and the ticket is stapled to the DMG

### Requirement: DMG distribution
The app SHALL be packaged as a DMG file for distribution via GitHub Releases or a project website. The DMG SHALL include the app bundle and a symlink to `/Applications` for drag-to-install.

#### Scenario: User installs the app
- **WHEN** the user opens the DMG
- **THEN** they see the app icon and an Applications folder shortcut, and can drag-to-install

### Requirement: Auto-update notifications
The app SHALL check for new versions on startup and periodically (daily). When a newer version is available on GitHub Releases, the app SHALL show a notification with a link to download the update.

#### Scenario: Update available
- **WHEN** the app detects a newer version on GitHub Releases
- **THEN** a notification is shown with the version number and a "Download" button

#### Scenario: No update
- **WHEN** the app is running the latest version
- **THEN** no notification is shown

### Requirement: Minimum system requirements
The app SHALL require macOS 26 (Tahoe) or later and Apple silicon (M1 or newer). The app SHALL display an error message and exit if launched on an unsupported system.

#### Scenario: Unsupported macOS version
- **WHEN** the app is launched on macOS 15
- **THEN** an alert is shown explaining the requirement for macOS 26+ and the app exits

#### Scenario: Intel Mac
- **WHEN** the app is launched on an Intel Mac
- **THEN** an alert is shown explaining the requirement for Apple silicon and the app exits
