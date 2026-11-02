# Web app design: Cluster theme

Appearance and copy only. API logic, data, routes and tests are unchanged, except the API's message text (absolute paths removed, phase numbers removed). Replaces the earlier teal theme; its tokens and styles are deleted, not layered over.

Source of the theme: the Cluster web repo (read-only; `DESIGN.md`, `globals.css`, `tailwind.config.ts`, `sticker.tsx`, `button.tsx`, `theme/`). Nothing was copied wholesale. Everything is plain CSS variables and classes in `src/app/styles.css`.

## Tokens taken

| Token | Dark (`:root[data-theme="dark"]`) | Light (default) |
|---|---|---|
| bg | 18 18 18 | 246 246 247 |
| card | 26 26 26 | 255 255 255 |
| raised | 34 34 34 | 240 240 242 |
| line | 44 44 44 | 225 225 230 |
| text | 245 245 245 | 24 24 27 |
| soft | 212 212 212 | 63 63 70 |
| muted | 163 163 163 | 95 95 104 |
| subtle | 115 115 115 | 130 130 140 |
| accent (lavender) | 203 166 247 | 148 102 220 |
| mint (good) | 166 227 161 | 47 125 34 |
| rose (problem) | 243 139 168 | 210 15 57 |

Bevel: dark hi `rgba(255,255,255,.05)` lo `rgba(0,0,0,.45)`; light hi `rgba(255,255,255,1)` lo `rgba(24,24,27,.08)`. Brand ink on lavender: `#1b1224`.

Also taken: Inter (variable, via `@fontsource-variable/inter`) for body and headings (500 to 700, `-0.02em`, `"cv11","ss01"`); Geist Mono (`@fontsource/geist-mono`) for `.font-nav` (navigation items and badges only); 6px / 4px corners; card bevel and input inset; the `.btn` family (primary, secondary, plain; 2px press); `.nav-active` raised tile; stickers (10% tint, coloured text, fine ring); 2px lavender focus outline; skip link; light default with a stored dark toggle and a before-paint script.

## Left out, and why

- Cluster name, logo, pixel glyphs, marble tiles, Pro star, verified stamps, rolling numbers, confetti, hazard ribbons, scanlines, chat styles: they are Cluster's identity, not a theme.
- Sky blue, peach, butter, `btn-light`, `btn-live`, `btn-danger`: they have Cluster-specific meanings. This app uses only lavender, mint, rose and grey.
- Tailwind, Next.js, `@apply`: this app is plain Vite and CSS.
- Animation: only the button press, simple colour transitions and the loading spinner (off under `prefers-reduced-motion`).

## Where the theme did not fit

- No chart palette in the theme. Charts use one lavender hue in four lightness steps (effect, mechanism, advise, int) and grey for false. Steps are darker in light mode and lighter in dark mode so each reads against the card (3:1 or better, checked in both themes; the 1px bar edge helps the lightest); the two middle steps carry hatching so they stay apart without colour. The chart is a horizontal bar chart (one row per split and class, labelled directly with the value at the bar end), so no legend is needed. Log axis and table view stay.
- Cluster has no "Ready / Not ready" status. Ready is mint (good news), Not ready and Coming soon are neutral grey, a failed request is rose.
- Cluster `.font-nav` is uppercase. Here it is used only for navigation, stickers and the small "Coming soon" sidebar heading. Table headings stay sentence case.
- Cluster icons are Phosphor. Used for the six screens and the theme toggle only: regular weight, grey; the current page in lavender.
- Coming soon pages: the sentence carries "Owner: to be confirmed" exactly; the list has Stage and Owner columns.

## Dashboard wireframe

```
+--------+------------------------------------------------------------+
| Medication Safety Support | Research prototype. Decision support only. Not medical advice. |
| Subareas A and B          +------------------------------------------------------------+
|        | Dashboard                                                  |
| [Dash] | Datasets and system status. Every figure ...               |
|  Med.  |                                                            |
|  Inter.| +-- System status ------------------------------------+    |
|  Alert | | Component | Status | What it found | What is needed |    |
|  Trace | | DDI corpus| READY  | XML train: 12 | Nothing        |    |
|  About | | DailyMed  | READY  | Label files   | Nothing        |    |
|        | |   Zip files: 1 | Total size: 1.87 GB | file.zip      |    |
| COMING | | Index     | NOT RD | Index missing | Build the index|    |
| SOON   | +----------------------------------------------------+    |
| Allergy|                                                            |
| ... Soon| +-- DDI class distribution (full width bars + table) --+   |
|        | +-- Real examples ---------------------------------------+ |
| [Theme]| +-- DailyMed labels ... ---------------------------------+ |
+--------+------------------------------------------------------------+
 mobile: 54px sticky header [menu] Title; menu opens a full-screen drawer.
```
