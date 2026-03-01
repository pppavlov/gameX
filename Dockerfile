FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libx11-6 \
    libxext6 \
    libxi6 \
    libxrandr2 \
    libxxf86vm1 \
    libxcursor1 \
    libfreetype6 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt pyinstaller

COPY . .

CMD ["python", "main.py"]
