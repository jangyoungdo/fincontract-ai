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
ARG E5_REVISION=8d923955b027282ba975c0a4c825486c9ca4c490
RUN python scripts/prepare_semantic_model.py download --destination /opt/models/multilingual-e5-small --revision ${E5_REVISION} \
    && python scripts/prepare_semantic_model.py verify --destination /opt/models/multilingual-e5-small --revision ${E5_REVISION}
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SEMANTIC_MODEL_PATH=/opt/models/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('/opt/models/multilingual-e5-small', local_files_only=True); assert len(m.encode(['query: offline integrity check'])) == 1"
RUN useradd --create-home --uid 10001 fincontract && mkdir -p /data/uploads /data/reports /data/chroma && chown -R fincontract:fincontract /data
USER fincontract
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
