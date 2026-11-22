# Colophon assets

The mark is an open book with a diamond printer's mark above it. The SVGs are
the masters; the PNGs are rendered from them.

## Colours

| Name     | Hex       | Use                                          |
|----------|-----------|----------------------------------------------|
| ink      | `#1F4FD1` | The brand blue. The mark, links, accents     |
| ink_dark | `#14327F` | Darker blue for hover, pressed and dark text |
| paper    | `#FFFFFF` | The mark on a blue background                |

## Files

| File                            | What it is for                                              |
|---------------------------------|-------------------------------------------------------------|
| `logo.svg`                      | Main logo: blue mark, transparent background. Use in the web UI header |
| `logo.png`                      | Same, 1024px PNG with transparent background                |
| `app-icon.svg`                  | Square app icon: white mark on full-bleed blue, no rounding |
| `app-icon.png`                  | Same, 1024px. For anywhere a square icon is needed (entry icon, store, launcher) |
| `favicon/favicon.svg`           | Favicon for modern browsers: white mark on a rounded blue square |
| `favicon/favicon.ico`           | Legacy favicon, holds 16, 32 and 48px                      |
| `favicon/favicon-16.png`, `favicon-32.png`, `favicon-48.png` | PNG favicons for browser tabs |
| `favicon/favicon-192.png`, `favicon-512.png` | Web app manifest icons                         |
| `favicon/apple-touch-icon.png`  | 180px iOS home screen icon (full-bleed square; iOS rounds it) |

Suggested head tags:

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#1F4FD1">
```
