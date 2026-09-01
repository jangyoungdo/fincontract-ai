FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor \
    && tesseract --version \
    && sha256sum /usr/share/tesseract-ocr/5/tessdata/kor.traineddata \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 fincontract && mkdir -p /data/uploads /data/reports /data/chroma && chown -R fincontract:fincontract /data
USER fincontract
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
