# YouTube uploads (Data API v3)

Aquaduct can upload finished renders to your YouTube channel using the **YouTube Data API v3** with OAuth 2.0 (desktop / loopback). This is **independent** of the TikTok toggle: enable YouTube only in **API → YouTube (Data API v3)**.

## Shorts

Shorts are determined mainly by **duration (≤ 60s)** and **vertical 9:16** video in your pipeline. For discovery, Aquaduct can add **`#Shorts`** to title/description when missing (**“Add #Shorts…”** checkbox in the API tab).

## Google Cloud setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **YouTube Data API v3** for that project.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Desktop app**.
4. Add an authorized redirect URI that matches the app, e.g. `http://127.0.0.1:8888/callback/` (same port as **OAuth port** in the API tab, default **8888** — different from TikTok’s default so OAuth servers do not clash).
5. Paste **Client ID** and **Client secret** into the API tab, **Save**, then **Connect YouTube account**.

Scopes used: `https://www.googleapis.com/auth/youtube.upload`.

## Tasks tab

With YouTube enabled and tokens saved, use **Upload to YouTube** on a selected task. Optional: **Auto-start YouTube upload when a render finishes** (separate from TikTok’s auto-upload).

## Privacy

Default upload visibility is configurable (**Private** / **Unlisted** / **Public**). Start with **Private** while testing.

## Security

- Do not commit `ui_settings.json` (contains OAuth tokens). Revoke or rotate credentials in Google Cloud if needed.

## See also

- [TikTok upload](tiktok.md) — inbox workflow via TikTok Content Posting API.

