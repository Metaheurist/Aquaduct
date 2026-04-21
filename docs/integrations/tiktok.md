# TikTok upload (Content Posting API)

Aquaduct can send finished `final.mp4` files to your **TikTok creator inbox** so you complete posting in the **TikTok mobile app** (recommended first integration). A **Tasks** tab lists each finished render; the **API** tab holds TikTok developer credentials and **Connect TikTok account**.

## Prerequisites

1. **Developer app** — Create an app at [TikTok for Developers](https://developers.tiktok.com/) and note the **Client key** and **Client secret**.
2. **Login Kit** — Configure a **redirect URI** that matches what you enter in Aquaduct (default: `http://127.0.0.1:8765/callback/`). The host must be `127.0.0.1` or `localhost`, include a **port**, and register the exact URI in the portal (you may use a wildcard port if TikTok supports it for your app).
3. **Scopes** — Aquaduct requests `user.info.basic` and `video.upload` for **inbox** uploads. **Direct post** to the profile requires `video.publish` and typically stricter [product review](https://developers.tiktok.com/).
4. **OAuth (PKCE)** — Desktop apps must use PKCE. Aquaduct starts a short-lived local HTTP server on the chosen port and opens the system browser for you to approve access. Tokens are stored in `ui_settings.json` on this machine; treat this file as sensitive.

## Inbox vs direct

| Mode | Scope | Behavior |
| --- | --- | --- |
| **Inbox** (default) | `video.upload` | Upload completes into the creator flow; **open the TikTok app** to add captions/hashtags and publish. Implemented in Aquaduct. |
| **Direct** | `video.publish` | Would post straight to the profile; **not fully wired** in Aquaduct yet — use Inbox mode. |

## User flow

1. Enter **Client key** / **Client secret** in the **API** tab (optionally adjust redirect URI and port to match your TikTok app settings).
2. Click **Save** (title bar) if you change fields, then **Connect TikTok account** and finish login in the browser.
3. After a pipeline run, open the **Tasks** tab — new videos appear automatically. Use **Copy caption** for title/description/hashtags from `meta.json` / `hashtags.txt`, or **Upload to TikTok** to push the file to inbox.
4. Optional: enable **Auto-start TikTok upload when a render finishes** to enqueue upload immediately after each successful render (still inbox-only in this version).

## Security

- Do not commit `ui_settings.json` (contains tokens).
- Revoke access from TikTok’s app permissions page if you rotate credentials.

## See also

- [YouTube upload](youtube.md) — separate enable and OAuth (YouTube Data API v3).

## References

- [Content Posting API — get started](https://developers.tiktok.com/doc/content-posting-api-get-started)
- [Upload video (inbox)](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video)
- [OAuth token management](https://developers.tiktok.com/doc/oauth-user-access-token-management)
- [Login Kit for Desktop](https://developers.tiktok.com/doc/login-kit-desktop)
