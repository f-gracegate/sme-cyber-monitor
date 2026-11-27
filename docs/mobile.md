# Mobile app (Phase 6)

A Flutter companion app for Android and iOS (`apps/mobile`). It doesn't try to be the analyst
workstation. It covers what owners and IT people need away from a desk:

| Tab | What it does |
| --- | --- |
| Overview | Posture score and confidence, open alerts, incidents, overdue tasks, coverage, latest alerts |
| Alerts | Open or resolved alerts by severity. The detail explains what was found, why it matters and what to do; "I'm on it" and Resolve (fixed, not a real problem, or expected) |
| Incidents | Active, mine and all. Report an incident (everyone). Responders change status, take ownership, close with an outcome, and add timeline updates |
| Tasks | The person's own fix and response tasks: Start, Mark done, Verify (managers) |
| More | Workspace switcher, notification inbox, push level, app lock, sign out |

Screens and buttons follow the same server-side permissions as the web app. Staff without alert
access don't see the Alerts tab, and see only their own incident reports.

## Sign-in and sessions

- Same accounts as the web dashboard, including two-step codes and recovery codes. A temporary
  password must be changed first. Organisations that require MFA send people to the web to set
  it up.
- `client: "mobile"` sessions get tokens in the response body (see [API.md](API.md)). The
  refresh token lives in the iOS Keychain (`unlocked_this_device`) or the Android Keystore, so it
  isn't copied into backups or onto other devices. Android backups are turned off for the app.
- Access tokens last 15 minutes and refresh automatically, one refresh at a time. A rejected
  refresh signs the person out. Mobile sessions last up to 30 days
  (`MOBILE_REFRESH_TOKEN_TTL_DAYS`).
- Optional **app lock** (Face ID, fingerprint or passcode), asked for on launch and after a
  minute in the background.
- The app refuses plain HTTP except to a developer's own machine (`localhost`, `10.0.2.2`). iOS
  App Transport Security allows only local networking. Android allows cleartext in debug
  builds only.

## Push notifications

1. Signed in, the app asks for notification permission and registers its FCM token
   (`POST /me/push-devices`). The token is stored encrypted, with a hash for de-duplication.
   The same phone used by someone else is reassigned, never shared.
2. The monitor worker turns new in-app notifications into pushes for each recipient's phones,
   if the notification meets their **push level** (default: high and critical). Anything older
   than 30 minutes is not pushed, because the inbox already has it.
3. The push says only `<Severity> · <Organisation>` and the alert or incident title. Tapping it
   opens the alert or incident (switching workspace if needed).
4. Pushes stop as soon as the session that registered the phone ends (sign-out, password change,
   revocation). Uninstalled apps are detected and disabled.

People manage their phones on the web under **Settings → Notifications** (remove, send a test).

## Building

```bash
cd apps/mobile
flutter pub get
flutter analyze && flutter test
# iOS simulator against the local API (http://localhost:8100)
flutter run -d "iPhone 18 Pro"
# Android emulator against the local API (http://10.0.2.2:8100)
flutter run -d emulator-5554
# Release builds
flutter build apk --release --dart-define=API_BASE_URL=https://api.example.com \
  --dart-define=FIREBASE_API_KEY=… --dart-define=FIREBASE_APP_ID=… \
  --dart-define=FIREBASE_SENDER_ID=… --dart-define=FIREBASE_PROJECT_ID=…
flutter build ipa --release --dart-define=API_BASE_URL=https://api.example.com …
```

Without the `FIREBASE_*` values the app works normally and shows "Push is not set up in this
build". CI analyses, tests and builds Android (release APK) and iOS (unsigned release) on every
push.

## Before store release (owner tasks)

- Apple Developer and Google Play accounts. Bundle IDs are `com.gracegate.smecm.smecmMobile` (iOS)
  and `com.gracegate.smecm.smecm_mobile` (Android).
- A Firebase project with the Android and iOS apps, an APNs key uploaded to Firebase, the Push
  Notifications capability and `aps-environment` entitlement in Xcode, and a service-account
  key for the backend (`FCM_SERVICE_ACCOUNT_FILE`).
- An Android upload keystore (CI currently signs release builds with the debug key) and Apple
  signing.
- App icons and store screenshots, privacy labels (data collected: name, email, device push
  token; no tracking), and a privacy policy URL.
- Android and iOS each ship once they pass their own device testing and security checks.
