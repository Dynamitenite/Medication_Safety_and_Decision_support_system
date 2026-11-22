# Backend image for Render (and any Docker host). Build context = the REPO ROOT:
#   docker build -f aakaash/Dockerfile --build-arg DATA_URL=<direct link to hosting_bundle.tar.gz> .
# The runtime data (catalogue, label index, appms, metrics) is NOT in git: it is downloaded once at build time
# from DATA_URL. Make it with aakaash/scripts/build_hosting_bundle.py. No keys are baked in: LLM_API_KEY and
# SESSION_SECRET come from the host's environment at run time.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 MALLOC_ARENA_MAX=2 \
    ENCODER=tfidf MEDSAFE_COOKIE_SECURE=1

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY aakaash/requirements.txt /tmp/requirements.txt
# server packages only: drop the test runner
RUN grep -vi '^pytest' /tmp/requirements.txt > /tmp/req-server.txt && pip install -r /tmp/req-server.txt

ARG DATA_URL
RUN test -n "$DATA_URL" || (echo "Set DATA_URL to the hosting_bundle.tar.gz link" && exit 1)
RUN curl -fSL --retry 3 "$DATA_URL" -o /tmp/bundle.tar.gz && tar -xzf /tmp/bundle.tar.gz -C /app && rm /tmp/bundle.tar.gz

COPY aakaash/api /app/aakaash/api
COPY aakaash/medsafe /app/aakaash/medsafe
COPY aakaash/scripts/seed_demo_account.py /app/aakaash/scripts/seed_demo_account.py
COPY aakaash/PAPER_TRACE.md /app/aakaash/PAPER_TRACE.md
COPY aakaash/start.sh /app/aakaash/start.sh

WORKDIR /app/aakaash
EXPOSE 8000
CMD ["sh", "start.sh"]
