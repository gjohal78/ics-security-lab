# Read-only web HMI.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# iproute2 for the zone-route entrypoint (used only in the segmented lab).
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --chmod: readable by the non-root user even if the host checkout is
# owner-only (0755 so directories stay traversable).
COPY --chmod=0755 . .

RUN useradd --system --no-create-home hmi
USER hmi

EXPOSE 8000
# zone-route.sh sets up routing (no-op in the flat lab) then runs gunicorn.
# One worker on purpose: the PLC poller and its 5-minute history live in this
# process. Threads let the web side answer while the poller runs.
ENTRYPOINT ["/app/zone-route.sh"]
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8000", "app:app"]
