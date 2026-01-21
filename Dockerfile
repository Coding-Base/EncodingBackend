FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install System Dependencies
# - ffmpeg: For video encoding
# - libpq-dev: For Postgres connection
# - gcc: For compiling python extensions
# - netcat-openbsd: For checking DB readiness
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        libpq-dev \
        gcc \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Copy Requirements
# Note: Ensure Dokploy Build Context is set to "/" (Root of Repo)
COPY requirements.txt /app/requirements.txt

# 2. Install Python Dependencies
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

# 3. Copy Application Code
# This puts 'config/' directly inside '/app/config/'
COPY . /app

# 4. Set Environment Variables
ENV FFMPEG_PATH=/usr/bin/ffmpeg
# Add the app directory to python path just to be safe
ENV PYTHONPATH=/app

# 5. Expose Port 8000
EXPOSE 8000

# 6. Run Migrations AND Worker AND Django via Gunicorn
# - "python manage.py migrate": Apply database migrations
# - "python -u worker_runner.py &": Runs the listener in background
# - "gunicorn ...": Runs the web server in foreground
CMD ["sh", "-c", "python manage.py migrate && python -u worker_runner.py & gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]