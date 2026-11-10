# Water-tank process simulator.
FROM python:3.12-slim

# Don't write .pyc files; flush output straight to `docker compose logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --chmod: readable by the non-root user even if the host checkout is owner-only.
COPY --chmod=0644 sim.py .

# Run as an unprivileged user; the simulator only needs outbound TCP.
RUN useradd --system --no-create-home sim
USER sim

CMD ["python", "sim.py"]
