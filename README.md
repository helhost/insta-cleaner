# Insta Cleaner

**A cleaner slate for your Instagram likes.**

A local Chrome extension that finds the likes you want to remove, then removes them after confirmation. Use your existing Instagram login—no separate account, server, or Python setup required.

## Choose what stays

- **Content:** reels, posts and carousels, or everything.
- **Authors:** everyone, people you follow, or people you don’t follow.
- **Dates:** a custom range, with progress as the scan runs.

See the number of matches before confirming removal. You can stop an ongoing scan or removal; requests already sent may still finish.

## Get started

1. Clone or download this repository.
2. Open `chrome://extensions` in Chrome and enable **Developer mode**.
3. Choose **Load unpacked** and select the repository’s `extension/` folder.
4. Sign in to Instagram, open the extension, and choose your filters.
5. Select **Find my likes**, then review the count and confirm removal.

Requires Chrome 116 or newer. After updating the files, reload the extension and refresh your Instagram tab.

## Local by design

The extension communicates with Instagram using your signed-in browser session. There is no project backend or external analytics. Scan data stays in the browser; the optional Python tools save their data locally.

This is an unofficial tool using Instagram’s web requests, which may change. A stopped or limited scan covers only the items collected. Author filters use author IDs inferred from Instagram’s media IDs; successful removal means Instagram acknowledged the request, not that every post was independently reloaded.

Currently supports **removing likes**. Comment and repost removal are not implemented.

## Development

The extension runs directly from source, with no build step. Python utilities are retained for investigation and regression testing.

[Contributing & testing](CONTRIBUTING.md) · [Extension architecture](extension/README.md) · [Development tools](tools/README.md)
