# Locked sandbox image. Build once while online (wheels vendored under wheels/ for offline rebuilds):
#   docker build -t nulllab-sandbox:latest .
# Run (done by sandbox/executor.py): docker run --rm --network=none --read-only --tmpfs /tmp -v <tmp>:/work -w /work nulllab-sandbox python run.py ...
FROM python:3.12-slim
RUN pip install --no-cache-dir scikit-learn pandas numpy
RUN useradd -m runner
USER runner
WORKDIR /work
