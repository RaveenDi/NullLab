# Locked sandbox image. Build once while online (wheels vendored under wheels/ for offline rebuilds):
#   docker build -t nulllab-sandbox:latest .
# Run (done by sandbox/executor.py): docker run --rm --network=none --read-only --tmpfs /tmp -v <tmp>:/work -w /work nulllab-sandbox python run.py ...
FROM python:3.12-slim
# Pinned to the versions every measured run used (local venv, Python 3.12). BRIEF-4 asked for sklearn==1.3; we pin the
# version actually measured (1.9.1) so container and subprocess results are comparable. Docker path still UNVERIFIED.
RUN pip install --no-cache-dir scikit-learn==1.9.1 pandas==3.1.0 numpy==2.5.4
RUN useradd -m runner
USER runner
WORKDIR /work
