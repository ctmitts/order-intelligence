FROM python:3.11-slim

# libgomp1 for onnxruntime (ChromaDB embeddings); pypdfium2 bundles its own
# PDF engine, so no system PDF library is needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/orders.csv ./data/orders.csv
COPY scripts/ ./scripts/

# Build the vector store at image-build time (also caches the embedding model).
RUN python scripts/build_db.py

EXPOSE 8501
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

CMD ["streamlit", "run", "app/streamlit_app.py"]
