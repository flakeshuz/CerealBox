# CerealBox

## Design Direction

CerealBox is a warm, playful personal workspace that feels simple, private, and
familiar. Every screen should be useful at a glance and easy to personalize.

## Principles

- **Calm by default:** Prefer quiet surfaces, clear hierarchy, and one strong action.
- **Fresh but flexible:** Use cereal-inspired warmth as a base, not a visual limit.
- **Configurable:** Design with named tokens and repeatable components.
- **Local and legible:** Important local/encrypted states should be clear without dominating.
- **Accessible:** Maintain readable text, visible focus, and clear contrast in every theme.

## Identity

- **Name:** CerealBox
- **Tagline:** Start your day, sorted.
- **Tone:** Friendly, direct, lightly playful
- **Default mood:** Milk cream, oat, berry red, and harvest green

## Customization Contract

Future themes and layout modes must change only configuration values, not component
structure or app behavior.

- `theme`: Named visual theme; default is `cereal`
- `color`: Surface, text, accent, success, warning, and destructive roles
- `density`: `comfortable`, `compact`, or future custom presets
- `font`: Family, size scale, and optional system-font preference
- `radius`: Control, card, and panel corner scales
- `layout`: Sidebar position, width, and navigation grouping
- `surface`: Solid, tinted, bordered, or custom card treatments
- `motion`: Duration and reduced-motion preference

No theme may redefine component meaning. For example, accent always means primary
action and destructive always means irreversible or harmful action.

## Foundation

Use semantic design tokens for all future UI work:

`background`, `surface`, `surfaceDim`, `text`, `textMuted`, `line`,
`control`, `controlHover`, `accent`, `accentSoft`, `success`, `warning`,
`destructive`, `focus`, `radius`, `spacing`, `typeScale`, and `density`.

Components use tokens directly. Hard-coded product colors and ad hoc spacing belong
only in theme configuration.

## Components

Keep the component set small and reusable:

- Page shell and sidebar
- Header and page title
- Card and card section
- Primary, secondary, quiet, and destructive buttons
- Text and select fields
- Segmented controls
- Lists and trees
- Tabs and navigation rows
- Dialog, status, and reminder surfaces

Components should expose themeable states: default, hover, active, selected,
disabled, focus, error, success, and warning.

## Layout

- Favor clear vertical hierarchy and generous reading order.
- Keep primary actions close to the content they affect.
- Use stable alignment rather than decorative borders.
- Preserve responsive behavior when sidebar width or density changes.
- Do not rely on color alone to communicate state.

## Personalization

Customization belongs in user settings and should update the app consistently.
Themes may include color, typography, density, radius, and layout preferences.
The app must preserve data and navigation behavior across every theme.

## Unified Experience

Every screen follows the same visual rhythm:

- A clear page title in the header
- Primary actions on the right in the accent style
- Secondary and destructive actions separated by intent
- Consistent 24px page gutters
- Shared surface, text, line, and state colors
- One list and dialog treatment across life areas
