FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir playwright==1.44.0 fastapi "uvicorn[standard]"

COPY refresher.py .

EXPOSE 8001

CMD ["python", "refresher.py"]
