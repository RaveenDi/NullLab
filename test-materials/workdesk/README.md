# Workdesk manual test materials

Use [the complete manual guide](../../docs/TESTING-WORKDESK.md) in this order:

- baseline.csv + notes.md: safe CSV-only generated baseline.
- notes-revised.md: test revision/plan invalidation without changing old results.
- supplied-pipeline/data.csv + train.py: exact copies of known synthetic confirmation case cn-b4m8, for testing uploaded-code execution and measured controls. Read the Python before acknowledging local execution.
- invalid-target.csv: deliberate yes/no labels, unsupported by the current 0/1 binary adapter.
- unsupported.json: deliberate unsupported upload extension.

Everything is synthetic test material. These are known development fixtures, not external researcher data, fresh held-out scientific evidence or accuracy benchmarks. PROVENANCE.json records exact supplied-fixture hashes. Do not reroll results until a preferred conclusion appears. Nothing starts a model call or classifier run merely by opening this folder.
