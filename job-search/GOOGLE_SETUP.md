# Connect JobPilot with Google

The app now supports Google OAuth and Gmail API sending. It does not require an app password. Google requires an OAuth client registration before a custom app can offer a working sign-in button. No real client credentials have been supplied to this installation yet.

## One-time setup

1. Open [Google Cloud Console](https://console.cloud.google.com/apis/credentials) using the account that will own your personal app configuration.
2. Select or create a project named JobPilot, and enable the Gmail API for that project.
3. Open Google Auth Platform. Configure the app name and contact details. For a personal Gmail account use an External audience. While the app is in Testing, add `afa974828@gmail.com` as a test user.
4. Configure data access for `https://www.googleapis.com/auth/gmail.send`, `openid`, and `email`. These let the app send mail and verify which account signed in. It does not request inbox-read or mailbox-modification permission.
5. Create an OAuth client with application type **Desktop app**, and download the client JSON. A Web application client will not work with this implementation.
6. Open JobPilot > Settings & connections > Sign in with Google > One-time Google app setup. Select the downloaded JSON and click **Save Google app configuration**.
7. Click **Sign in with Google**. Your normal system browser opens. Sign in as `afa974828@gmail.com`, review the requested permission, and choose whether to grant it. JobPilot rejects a different account or a grant that omits sending permission.
8. After the confirmation page, return to JobPilot and click **Test Google connection**. This checks authentication without sending a message.

Google may still ask for an account security check. Google OAuth is not a way to bypass required Google security checks. While an External app remains in Testing, Gmail refresh tokens normally expire after seven days, requiring reconnection. Publishing and verification requirements depend on the app's use; follow Google's console guidance rather than assuming this personal configuration is approved for public distribution.

## What is implemented

- Desktop loopback redirect on a temporary localhost port.
- Random state and S256 PKCE, ten-minute authorization expiry, and matching account validation.
- Windows DPAPI encryption for the client configuration and tokens.
- Offline access with automatic access-token refresh for scheduled runs.
- Gmail API `messages.send` with the existing MIME body and resume attachment.
- No success recorded without a Gmail message ID. As with SMTP, API acceptance does not mean the employer read the email.
- Client configuration and access/refresh tokens are never returned by the dashboard API or printed in logs.

No live Google sign-in or live Gmail sending can be verified before the client registration and user consent are complete.

Sources: [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [Gmail sending](https://developers.google.com/workspace/gmail/api/guides/sending), [refresh-token expiration](https://developers.google.com/identity/protocols/oauth2/#expiration).
