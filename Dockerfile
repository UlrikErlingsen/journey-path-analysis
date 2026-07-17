FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARROW_DEFAULT_MEMORY_POOL=system

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Application code stays root-owned; the runtime user only needs a writable home.
RUN useradd --create-home --uid 10001 tracesignal
USER tracesignal

EXPOSE 8585
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8585/_stcore/health')"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8585", "--browser.gatherUsageStats=false"]
