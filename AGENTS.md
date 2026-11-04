# Contributor notes

- Python 3.12. Install with `pip install -r requirements-dev.txt`; run `python -m pytest -m "not live" -q`.
- Model access is bring-your-own-key: copy `.env.example` to `.env` and set `MODEL_API_KEY`. Never commit `.env`, keys or run output that contains them.
- Do not hard-code absolute paths or machine-specific tooling.
- Keep documentation to what a user or contributor needs. Do not record work logs, status diaries or review transcripts in the repository.
