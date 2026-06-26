# Bill Teaching Assistant

Chrome extension prototype for Bill Teaching Mode only.

It observes a teaching page and sends context and interaction metadata to Bill Core. It does not automate clicks, typing, or workflow execution.

## What it captures

- Current page URL, title, and domain
- Visible buttons, fields, links, and headings
- Click, focus, input, and change metadata
- Selector candidates and nearby labels for targets
- Redacted input metadata only

## Load instructions

1. Open `chrome://extensions` in Chrome.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `chrome-extension/bill-teaching-assistant`.
5. Open a TrackVia page such as `https://go.trackvia.com/#/signin`.
6. Open the extension popup.
7. Paste the active Bill Teaching Mode session id.
8. Click Connect.
9. In the popup, confirm `Content active` and run `Test send context`.

## Profile requirement

- The extension must be loaded in the same Chrome profile as the teaching tab.
- If Teaching Mode opens Chrome with a dedicated `--user-data-dir`, load this unpacked extension in that profile as well.
- If popup diagnostics show `Content inactive`, pairing can still look valid in storage while no events are emitted from the teaching tab.

## Notes

- The extension never runs workflows.
- The extension never clicks, types, submits, or automates anything.
- It only observes while paired to an active session.
- Backend endpoint used: `POST /api/teaching/session/{session_id}/extension-events`