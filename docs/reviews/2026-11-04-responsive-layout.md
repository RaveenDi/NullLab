# Responsive workspace — 4 November 2026

The owner requested viewport-sized sections, comparable desktop/mobile usability, and a corrected header logo. This changes presentation and navigation; the audit engine, scientific results and Meta prompts are unchanged.

## Implemented

- Main sections use the available viewport height after the sticky header. Header size is measured when available, with CSS fallbacks and device safe-area spacing.
- Desktop retains side-by-side setup/results. Tablet and phone layouts use explicit Study setup / Audit result buttons. Starting or opening a result selects the result view; clarification returns to setup. Polling does not take the user out of setup.
- Saved audits are a separate section. All primary navigation destinations remain available on mobile; the read-only demo hides its unavailable history destination.
- Setup and evidence have named, keyboard-focusable scroll regions. The run action remains outside the setup scroll area. Expanded forms, long evidence and tables remain reachable. Short landscape windows and zoom-equivalent layouts reflow vertically instead of shrinking text or clipping content.
- Conclusions and measurements precede extended research-room evidence. Detailed plans, traces and provenance are progressively disclosed. Status/error feedback is outside both mobile panes so import errors remain visible.
- Inputs use 16px text, primary navigation and actions have 44px minimum height, focus indicators include textareas, and explicit navigation respects reduced-motion preferences. Result headings announce conclusion changes without repeatedly announcing unchanged text during polling.
- Header and footer use a consistent inline vector circle/slash mark with the NullLab wordmark, replacing the font-dependent badge and trailing dot.
- The portable demo's recording-script insertion handles formatted HTML attributes and fails closed if its required script cannot be inserted.

## Verification

Focused client and local-asset checks: **19 passed**, one dependency deprecation warning. See out/responsive-workspace-tests-release.xml. Repository Ruff, JavaScript parsing, CSS parsing and historical freeze checks pass. This is separate from the earlier 88-test integration and 81-test packaged-source checks, not an additional claim about their coverage.

Offline Chromium component renders exercised **60 fixed states across ten viewport sizes**: 1440×900, 1366×768, 1280×720, 1024×768, 768×1024, 390×844, 375×667, 320×568, 844×390 and 320×256. States include the initial local fixture, recorded evidence, the actual portable demo, expanded setup and expanded evidence. HTTP(S) was blocked, only fixture files were loaded, and no real audit/API/model call was started. These were fixed rendering checks, not an application walkthrough or end-user study.

No horizontal page overflow was detected. All main sections fit the eight standard portrait/desktop viewport sizes. Landscape marketing sections fit; the long landscape workspace and zoom-equivalent layouts deliberately reflow. Expanded content and run controls remained reachable. The initial smallest-phone overflow was corrected before the final checks. Recordings made zero API requests. Artifacts remain under out/responsive-layout; out/responsive-layout-latest.json identifies the latest render run.

No physical Safari/Android device, assistive-technology session or outside-user usability study was performed. Safe-area styling is implemented, not a claim of physical-device certification. Standards references: [viewport lengths](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/length), [W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) and [target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

The first pushed build's separate repository CI remains an open issue: [run 41696111945](https://github.com/RaveenDi/NullLab/actions/runs/41696111945) passed lint/freeze and reported 459 passed, one historical G9b runner test failed, 78 skipped and four deselected. This responsive work does not claim to repair that failure. Changes are local; no additional commit, push, hosted deployment or submission is performed by this task.
