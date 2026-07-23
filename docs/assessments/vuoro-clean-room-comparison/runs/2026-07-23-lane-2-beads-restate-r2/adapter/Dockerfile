FROM python:3.12-slim
WORKDIR /app
COPY adapter.py /app/adapter.py
RUN pip install --no-cache-dir 'restate-sdk[serde]==1.0.2' 'hypercorn==0.18.0'
CMD ["hypercorn", "--bind", "0.0.0.0:9080", "adapter:app"]
