# Design system

Internal HR / finance operations tool: restrained, dense, readable. Tokens live in `frontend/src/styles.css`;
components in `frontend/src/components/ds/index.tsx`. Nothing is decorative: no gradients, glow, blur, emoji icons,
pill shapes or illustrations.

## Colour
| Token | Value | Use |
|---|---|---|
| `--bg` / `--surface` / `--surface-muted` / `--sidebar` | #f4f3f0 / #fff / #faf9f7 / #ecebe7 | page, panels, zebra rows, sidebar (warm grays) |
| `--border` / `--border-strong` | #dedbd5 / #c2beb5 | hairlines / control borders |
| `--text` / `--text-muted` | #25272b / #5f636c | charcoal text |
| `--primary` (+ hover, soft) | #1f3a5f | the only accent: primary buttons, links, active nav, focus ring |
| `--success` / `--warning` / `--danger` | #1d6b3f / #7d5300 / #a32a2a (+ `-bg`, `-border`) | status, validation, exceptions **only** |

## Type and spacing
IBM Plex Sans (self-hosted via `@fontsource`, no CDN), IBM Plex Mono for IDs. Base 14px; scale 12/13/14/16/20.
Numbers use `font-variant-numeric: tabular-nums` and are right-aligned (`.num`). Spacing scale 4/8/12/16/24/32.
Radius 3px everywhere (4px dialogs). Controls are 32px high (26px small).

## Components
- **Button**: default, primary, danger, ghost, `sm`. **LinkButton** for navigation styled as a button.
- **Field / TextField / SelectField**: explicit visible label, required marker, hint, inline error (`role="alert"`),
  `aria-invalid` + `aria-describedby` wired automatically. Numeric inputs right-aligned.
- **Table** (`.table`): compact, sticky header, zebra rows, sortable headers are real `<button>`s inside `<th aria-sort>`,
  caption for screen readers, `aria-busy` while loading.
- **Badge**: neutral / success / warning / danger. Status is always text, never colour alone.
- **Alert**: danger / warning / success / info banner with icon. **EmptyState / ErrorState / Spinner** for the three
  non-happy data states; error state always shows the server's message and a Retry.
- **ConfirmDialog** (Radix Dialog): focus trap, Esc closes, restores focus; used for every consequential action.
- **Toast**: polite live region for success confirmation. **PageHeader** with breadcrumbs and right-aligned actions.
- **Icons**: `lucide-react` only, 14-16px, always `aria-hidden` next to a text label.

## Patterns
- Loading: skeleton rows on first load; previous data dimmed while refreshing. Loading is never shown as "empty".
- Validation: client-side mirrors server rules for fast feedback; server errors are always displayed and mapped to fields.
- Destructive/consequential actions: confirmation dialog stating exactly what will and will not happen.
- Permissions: the UI hides actions a role cannot use, but the server is the authority (every endpoint checks).
- Navigation lists only sections that exist; new sections are added as each phase ships.
- Layout: sidebar (collapses to icons below 900px), 48px top bar, content max-width 1280px. Desktop, laptop and tablet widths.

## Accessibility notes
Visible focus ring (2px navy), keyboard-operable everything (native controls + Radix), semantic landmarks
(`nav`, `main`, `header`), reduced-motion respected for the spinner. Contrast: charcoal on white/warm gray;
status colours are dark text on pale backgrounds. **Not yet verified:** automated axe audit and screen-reader pass.
