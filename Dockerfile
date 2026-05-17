FROM python:3.11-slim

LABEL maintainer="Chatchai Tritham <chatchait66@nu.ac.th>"
LABEL repository="DRAS-5"
LABEL description="Reproducible research container for DRAS-5"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN pip install -e .

CMD ["python", "-m", "pytest", "tests", "-q"]
