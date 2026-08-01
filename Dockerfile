FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY pension-planner.html .
COPY server server

EXPOSE 8000
# Two workers is ample for ~100 concurrent sessions: requests are small JSON
# reads/writes; all heavy computation (projections, Monte Carlo) runs in the
# browser. Scale workers/replicas only if measurements say so.
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
