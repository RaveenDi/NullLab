# Current product and retained history

The current product is the v2 author workspace described in [README](../README.md), [usage](USAGE.md), [architecture](ARCHITECTURE.md), [deployment](DEPLOYMENT.md) and [release status](RELEASE-STATUS.md). The [documentation index](README.md) is the starting point. Dated research notes do not override those guides or describe every subsequent UI change.

## Active implementation

- agent.engine, agent.study, agent.intake, agent.provider, agent.evidence, agent.assessment and agent.storage implement supported audits and evidence handling.
- app/server.py and app/static implement the local workspace and recorded frontend.
- agent.edit_dsl, agent.contract_g9, agent.guard_g9 and the current sandbox modules remain active dependencies. Their older names do not make them unused code.
- The supported CLI is nulllab / python -m agent.engine; nulllab_cli.py audit routes to the same engine. agent.ci_check defaults to that engine.
- Public SECOM inputs and the two fixed synthetic cohorts retain their exact identities. Private generated cases and runtime output are ignored.

## Retained at original paths

| Material | Status and purpose |
|---|---|
| Numbered docs/EVAL reports and preregistrations | Historical experiment protocols/results. Preserve original claims, failures and instrument provenance. Current v2 pilot/follow-up reports are linked separately in the index. |
| Dated pre-rebuild reports in docs/reviews | Findings about the source state audited on that date. Later completion and UI reports describe the repairs; original findings are not silently rewritten into passes. |
| agent/factorial generation runners, generation entry modules, historical evaluation builders | Earlier research runners and compatibility paths. Some tests still import them; they are not the advertised author workflow. |
| report/ and historical real/ or runs directories | Earlier presentation/research artifacts. They are not the current app or submission hero. The curated release excludes retired domain data/results. |
| Old builder briefs and killed-idea plans | Development history, not current implementation requirements. Private briefs remain ignored. |

These files were not all deleted. Frozen records require their original paths and hashes; other historical modules remain imported by compatibility/tests. Removing or moving them without dependency and provenance work would break reproducibility. [Frozen-file rules](FROZEN-FILES.md) and the changelog govern deliberate changes. The original hash manifest is not regenerated to hide changes.

## Cleanup boundary

Active guides and navigation use the v2 workspace, current examples and current deployment boundaries. Stale private-tooling names were removed from current setup/architecture prose. The README starts from bundled public data instead of requiring regeneration of already included cases. Historical references remain in dated records and compatibility code where they explain what actually ran.

scripts/package_source.py uses an explicit allow-list for the public source subset. scripts/package_demo.py packages recorded public evidence and disables fresh execution. Neither command packages private user cases, credentials, arbitrary adjacent files or the complete historical working tree. Generated local QA output is retained under ignored out; it is not a current scientific success rate.

The separate parent MetaHackathon planning directory is outside this app's release subset. This cleanup does not claim that every old Markdown file in that planning workspace, or every old compatibility module in this repository, has been removed. No frozen data, preregistration or original result was deleted by the UI/documentation work.
