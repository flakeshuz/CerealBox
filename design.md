# CerealBox UI Design Plan

## Purpose and direction

CerealBox is a native PyQt6 desktop application for personal information and life management. The next UI work should make its existing workspace easier to scan, more consistent, and more complete without replacing its warm, personal character or redesigning every screen at once.

**Recommended direction:** preserve the cream-and-terracotta CerealBox identity; make important information and next actions clearer; establish reusable UI patterns; then improve one complete workflow at a time. Use established design systems as sources of principles, not as visual templates to copy.

This is a research-backed plan, not an implemented design specification. Confirm product decisions such as supported document formats before implementing the relevant features.

## Avoiding analysis paralysis

Use this document to guide the next small improvement, not as a prerequisite to redesigning every screen.

- Limit discovery to one pass over the target workflow and the references below. Do not keep searching for a perfect design system or wait for a complete application-wide audit.
- Choose one user-visible slice, implement it end to end, and review the result before expanding scope.
- Make unresolved, non-critical choices using the defaults below. Revisit them only when user feedback or implementation evidence shows they are wrong.
- Improve shared styles when the first slice needs them; do not make a comprehensive token system a gate for shipping that slice.
- Keep deferred work visible, but do not pull it into the active slice without a concrete reason.

**Defaults for the first slice:** treat navigation—not individual module redesign—as the first UI problem. Show Today, Calendar, Tasks, and Money as the primary workspaces; put the other modules under an expandable “More” area, preserving their current categories. Keep every module available. Defer favorites, custom ordering, and module removal until there is evidence they are needed.

## Current UI snapshot

### Application shell and navigation

- [ui/shell.py](ui/shell.py) builds a native `QMainWindow` with a persistent sidebar and a stacked page area.
- The header shows the page name and date, plus contextual “+ Event” and “+ Task” actions. The status bar reports “Local and encrypted.”
- The shell provides backup, JSON import/export, password, density, and keyboard-shortcut actions. Existing shortcuts include `Ctrl+1`–`Ctrl+4` for primary workspaces, `Ctrl+N` for a new item, `Ctrl+K` to find a workspace, and `F1` for the shortcut list.
- [modules/__init__.py](modules/__init__.py) registers 15 workspaces: Dashboard, Calendar, Tasks, Money, Taxes, Document Vault, Notes, Contacts, Habits, Health, Home, Passwords, Goals, Search, and Email.
- [ui/sidebar.py](ui/sidebar.py) groups spaces into Daily, Personal, and Library sections and filters navigation titles, but currently presents all registered workspaces as navigation choices. This makes 15 distinct areas compete for attention before a user has chosen what to do.
- The first four shortcuts already establish a useful default core: Today (Dashboard), Calendar, Tasks, and Money. The shell's quick actions also emphasize events and tasks.
- The shell initially sets a minimum size of 820×540, then adjusts the minimum size during startup based on screen availability (up to 900×560). Test the actual supported compact size as part of UI work.

### Visual system

- [ui/theme.py](ui/theme.py) defines a warm cream surface, dark brown text, and terracotta accent, with shared widget styling.
- Comfortable and dense spacing modes are already available and persisted through the shell.
- [ui/components.py](ui/components.py) has a small shared set of page-header, page-surface, and list helpers.
- Several screens add their own local styles. A small, semantic token and component vocabulary would help keep those screens consistent without losing the existing palette.

### Main workspaces

- [modules/dashboard/ui.py](modules/dashboard/ui.py) supports customizable cards. Quick actions, Tasks, and Today are shown by default; Week, Budget, Links, and Bills can be added. Dashboard cards refresh from application data.
- [modules/tasks/ui.py](modules/tasks/ui.py) already has Open/Today/Done/All filters, task-and-tag search, selection actions, reminders and repeat settings, and keyboard shortcuts. Retain these useful capabilities while improving consistency and scanability.
- [modules/docsvault_ui.py](modules/docsvault_ui.py) currently adds text through a small dialog and lists document names and a “Size (bytes)” column. It does not yet provide search, a document detail/preview workflow, or deletion controls.
- [modules/docsvault.py](modules/docsvault.py) already supports putting, getting, listing, and deleting documents. It stores document content as Base64 text in the encrypted vault.
- **Document size display needs care:** the current UI measures `len(data)` on the stored Base64 string, so the displayed count is not the original file’s byte size. A polished listing should calculate and label size accurately.
- [modules/notes/ui.py](modules/notes/ui.py) lists notes and supports adding one; opening and managing existing notes could be considered in a later consistency pass.

### Existing frontend tests

[tests/test_qt_frontend.py](tests/test_qt_frontend.py) verifies that registered module screens are widgets, that basic navigation and sidebar filtering work, and that password entry is validated. Add focused tests for new UI behavior as it is introduced rather than broad snapshot coverage.

## Design principles for CerealBox

1. **Make the next useful action obvious.** Give each screen a clear primary purpose and a prominent main action. Keep secondary actions available without giving them equal visual weight.
2. **Optimize for scanning.** Put the most important information first; align related content; use headings, spacing, and restrained grouping to communicate hierarchy.
3. **Keep the experience predictable.** Reuse the same patterns for search, selection, create/edit dialogs, confirmations, empty states, and status messages across workspaces.
4. **Use progressive disclosure.** Keep everyday views focused and put less-frequent controls, such as dashboard customization, behind an explicit action.
5. **Use color semantically.** Keep most text neutral and reserve the accent for emphasis, focus, selection, and primary actions. Pair status colors with text or icons; color alone must not communicate meaning.
6. **Keep language plain and direct.** Prefer concise labels that describe the action or state. Avoid unexplained jargon and ambiguous icon-only controls.
7. **Support user control and accessibility.** Preserve keyboard access, visible focus, readable text, helpful labels, and adaptable layouts. Test contrast and text scaling instead of assuming the palette is accessible.
8. **Preserve trust.** CerealBox handles personal data and advertises local encryption. UI copy about storage, sync, import/export, and backups should be accurate and explicit, especially when an action creates an unencrypted export.

## Recommended roadmap

### 1. Reduce navigation overload without removing modules

Make the information architecture the first UI improvement; do not redesign all 15 workspaces in parallel.

- Show **Today**, **Calendar**, **Tasks**, and **Money** as the primary “Core” workspaces, matching the existing first four shortcuts.
- Put the other 11 modules under a collapsed **More** area. Preserve the existing groupings inside it: Daily (Notes, Habits, Goals), Personal (Taxes, Health, Home, Contacts), and Library (Document Vault, Passwords, Search, Email).
- Keep all modules and their data intact and reachable. This is a navigation hierarchy change, not a feature removal or a judgement that secondary modules are unimportant.
- Make navigation filtering search all workspaces, including collapsed groups; reveal matching results while a query is active, then restore the collapsed state when the query is cleared.
- Preserve `Ctrl+K` as “find a workspace.” Keep the Search module’s purpose distinct unless its current behavior is deliberately redesigned; do not imply `Ctrl+K` searches document or life-area content.
- Do not add a module picker, favorites, per-user ordering, or new categories in this first change. Revisit those only after observing that the simpler hierarchy is insufficient.

**Outcome:** users first see a manageable set of common destinations, while every existing workspace remains discoverable in one predictable place.

### 2. Add only the shared foundations the next slice needs

Use the existing [ui/theme.py](ui/theme.py) and [ui/components.py](ui/components.py) rather than introducing a new design framework or blocking on a full design-system rewrite.

- Reuse the current palette and spacing modes; add or adjust only what the navigation change and next workspace slice require.
- Keep headings, controls, focus, empty/error states, and confirmation behavior consistent within touched screens.
- Check contrast for changed controls and text against the actual CerealBox palette.
- Extract a shared helper only when a change demonstrates that it will be reused.

**Outcome:** changes fit the existing UI without making an application-wide design-system project a prerequisite.

### 3. Complete a bounded Document Vault slice

After reducing navigation clutter, the Document Vault is the next bounded workspace improvement: its current UI is a text-entry/list prototype, while its module already supports basic document operations.

For the first increment, keep the current text-based add flow and add only:

- Search by document name.
- A selected-document text detail/preview.
- Confirmed deletion.
- An accurate byte count for stored text content.
- Clear empty and operation-error states.

Preserve existing records and add focused tests for search, byte count, and deletion behavior. Defer arbitrary file import, external opening, folders/tags, and file-size limits; those decisions are not needed to deliver this first increment.

**Outcome:** users can find, inspect, and safely remove documents without changing the existing storage format.

### 4. Refine the Today experience

Treat the dashboard as the daily starting point, not a place to show every possible metric.

- Make today’s events, due tasks, and overdue tasks easy to distinguish and scan.
- Prioritize actionable items and clear empty states; keep secondary information quieter.
- Review the dashboard’s Quick actions alongside the shell’s contextual “+ Event” and “+ Task” buttons to avoid competing entry points.
- Keep customization available but secondary to using the dashboard.
- Verify the layout at the smallest supported window size and with dense spacing.

**Outcome:** a user can quickly tell what needs attention today and how to act on it.

### 5. Bring common patterns to the other workspaces

- Reuse the shared design foundations in Tasks and Notes first, then apply them to the remaining modules.
- Improve workspaces in response to user needs; do not treat the number of registered modules as a requirement to polish or expand each one.
- Review whether each list screen has a clear search/selection model, useful empty state, predictable editing, and safe destructive actions.
- Keep existing task keyboard workflows and dashboard customization working.
- Review navigation grouping and filtering as the number of workspaces grows. `Ctrl+K` currently finds a workspace; do not describe it as global content search unless that behavior is added.

**Outcome:** switching workspaces does not require relearning basic interaction patterns.

### 6. Validate the slice and iterate

Validate the active slice with real workflows, then move to the next roadmap item only after the current one works:

- Navigate to a workspace using the sidebar and `Ctrl+K`.
- Confirm the primary navigation shows only the four core workspaces by default and that every other workspace remains reachable under “More.”
- Search for a workspace inside a collapsed group and confirm its result is revealed and can be opened.
- Review Today and identify the next task or event.
- Create, find, complete, and edit a task using both pointer and keyboard.
- Add, find, inspect/open, and delete a document once the vault workflow is defined.
- Exercise empty data, invalid input, and failed operations; ensure errors are visible and understandable.
- Check layout at the actual minimum supported size and in comfortable and dense modes.
- Check keyboard-only use, visible focus, tab order, accessible names/labels, readable text, and contrast.
- Add focused Qt tests for new interactions and regressions, following the style of [tests/test_qt_frontend.py](tests/test_qt_frontend.py).

**Stop condition:** once the active workflow works, its main states are covered, and the acceptance checklist passes, ship that slice. Do not delay it for unrelated polish or a complete redesign.

## Acceptance checklist

A UI slice is ready when:

- Its primary task and action are apparent without explanation.
- Empty, normal, and error states have been considered.
- Labels and status do not depend on color alone.
- Keyboard navigation and visible focus work for the main workflow.
- Destructive actions are deliberate and clearly identified.
- The screen remains usable at the supported compact size and in both density modes.
- Text and controls have been checked for sufficient contrast and readable sizing.
- Existing data and behavior remain compatible, and focused tests cover the behavior introduced.

For contrast, use WCAG AA as a practical baseline: at least 4.5:1 for normal text and 3:1 for large text. Also check non-text controls and focus visibility. These measurements are design checks; validate the Qt interface directly rather than assuming web guidance maps perfectly to native widgets.

## Research and inspiration

These are official design-system or product-design resources. Their most useful contribution is repeatable guidance and patterns; CerealBox should adapt those principles to a native desktop app rather than copy web-specific components.

### Apple Human Interface Guidelines

- [Layout](https://developer.apple.com/design/human-interface-guidelines/layout.md): order content by importance, align and group related elements, use progressive disclosure, and design for changing window sizes and text lengths.
- [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility.md): make interactions intuitive, information perceivable through more than one signal, and interfaces adaptable to user needs. The guidance also recommends readable text and sufficient contrast.

**Useful for CerealBox:** prioritizing Today content, handling compact windows, and designing keyboard and accessibility behavior as part of the interface.

### Google Material Design 3

- [Material Design](https://m3.material.io/): Google’s design system provides guidance, styles, and components for building user-friendly interfaces.

**Useful for CerealBox:** treat visual styles and components as a coherent system instead of accumulating one-off widget styles. Use this as a reference for system-level consistency, not as a reason to adopt Material’s web or mobile appearance.

### Shopify Polaris and App Design Guidelines

- [App Design Guidelines](https://shopify.dev/docs/apps/design): predictable interfaces that fit users’ established workflows build trust; consistency is preferable to difference for its own sake.
- [Visual design](https://shopify.dev/docs/apps/design/visual-design): use typography to establish hierarchy; use color intentionally for state; do not rely on color alone; maintain readable contrast.
- [Using Polaris web components](https://shopify.dev/docs/api/polaris/using-polaris-web-components): emphasizes labeled form controls, heading hierarchy, keyboard testing, and accessibility built into component use.

**Useful for CerealBox:** consistent screen patterns, clear form labels, and restrained status colors—especially for vault operations and calendar sync.

### GitHub Primer

- [Primer Accessibility](https://primer.style/accessibility/): organizes accessibility foundations, design guidance, component patterns, and accessible messaging.
- [Design guidance](https://primer.style/accessibility/design-guidance/): highlights focus management, color considerations, links and buttons, motion, and text resizing.
- [Primer Primitives](https://primer.style/product/primitives/): documents shared tokens for color, spacing, and typography, including high-contrast and color-vision-related themes.

**Useful for CerealBox:** keep focus behavior, status messaging, contrast, and design tokens in the shared foundation rather than treating accessibility as a final audit.

### Atlassian Design System

- [Accessibility](https://atlassian.design/foundations/accessibility/): recommends consistent patterns, simple language, user control, text alternatives, accessible color contrast, and broad testing.
- [Color](https://atlassian.design/foundations/color/): describes color as a tool for consistent meaning across experiences.

**Useful for CerealBox:** plain-language labels, consistent workflows, preferences that respect user needs, and broad keyboard/accessibility checks.

## Scope note

[run.sh](run.sh) is the Python/package launcher, not a UI implementation surface. The UI roadmap does not require changing it.
