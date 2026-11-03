# Compact shell, focus workspace and deployment review — 4 November 2026

This follows the original responsive-layout report. The audit engine, prompts, scientific controls and recorded results are unchanged. The changes are local; no new commit, push, cloud deployment, domain purchase or hackathon submission was performed.

## Implemented interface

- Header base height is 60px on desktop and 56px on phones, plus applicable safe-area space. The vector wordmark is centered. Desktop navigation is split left/right; phones use an accessible menu with Escape/outside-click/link dismissal.
- Footer is a compact event credit and source link. The duplicate logo/name and tagline were removed.
- Landing entrance, ring and evidence-label animation is finite, with no simulated agent progress. It settles automatically and is disabled for reduced motion.
- Author Workspace fills the available screen on ordinary desktop/portrait and landscape sizes. Fullscreen fills the browser screen; unsupported/denied native fullscreen retains a viewport focus view. Exit/Escape restore interaction and prior focus.
- Focus mode locks background page scrolling, makes outside content inert, contains keyboard focus and preserves the active audit, cancellation target and selected mobile pane. Long forms/evidence remain independently scrollable. Zoom-equivalent very short layouts reflow; a complete form cannot be forced into arbitrarily small space without losing readability.
- Native browser fullscreen exit and rejected-entry/rejected-exit cases update state honestly. The shell performs no audit or provider request.

## Checks

**26 focused offline checks passed**: client state/lifecycle and local asset delivery, including fullscreen fallback, native state changes, denied entry/exit, Escape, mobile menu dismissal, active-job preservation, read-only recordings and reduced-motion navigation. One TestClient dependency deprecation warning remains. See out/workspace-shell-tests.xml.

Offline Chromium component checks exercised **102 fixed states at ten sizes**: 1440x900, 1366x768, 1280x720, 1024x768, 768x1024, 390x844, 375x667, 320x568, 844x390 and 320x256. They cover initial/recorded/packaged pages, expanded setup/evidence, mobile menus and viewport focus. HTTP(S) was blocked; public fixtures were used and no real API/model call was made. This was not an application walkthrough or an external-user study.

No horizontal page overflow was found; expanded content/run actions remained reachable. Standard sections fit the viewport, including the ordinary landscape workspace. The 320x256 zoom-equivalent case deliberately reflows. The native fullscreen API entered successfully in the offline desktop renderer; phone-native fullscreen is not certified. The prior hidden-menu touch-target check was corrected to count rendered controls, and menu-open targets were then checked explicitly.

Eleven finite animation instances settled after 4.2 seconds; reduced motion disabled them all. Focus fallback occupied the viewport at every tested size and restored background interaction on exit. Artifacts are identified by out/responsive-layout-latest.json; each render run is retained separately. No physical iOS/Android or assistive-technology session was performed.

## Documentation and deployment

Eleven current guides were checked for local and curated-release links, with no missing targets. Current README/usage/architecture/deployment guidance was aligned with the shell. Unnecessary default data regeneration and old private-tooling names were removed from active setup prose. [History](../HISTORY.md) and the [review index](README.md) distinguish retained frozen evidence and compatibility code from current product documentation. Historical files were not all deleted or relocated; original records and failures retain their provenance.

[Deployment](../DEPLOYMENT.md) now documents a concrete AWS Amplify static-ZIP/custom-domain path, the separate proposed authenticated fresh-audit service, and the roles of Meta/Baseten/Modal infrastructure. Localhost alone is not judge-accessible. No unsupported claim that the current local server is production-hosted is made.

The first pushed build's unrelated historical G9b runner CI failure remains open (459 passed, one failed, 78 skipped, four deselected). Focused UI checks do not convert that failure into a pass. The original scientific cohorts remain unchanged and no new accuracy/user-impact score is claimed.
