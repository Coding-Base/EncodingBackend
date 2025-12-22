# EncodingBackend Service

Standalone microservice for video encoding. This service handles the CPU-intensive task of converting uploaded videos to HLS format for adaptive streaming.

## Architecture

```
MainBackend (Django)
    ↓ (1. Video uploaded to S3)
    ↓ (2. Queue encoding job to Redis)
Redis Queue
    ↓ (3. EncodingBackend polls Redis)
EncodingBackend (Django)
    ↓ (4. Download video from S3)
    ↓ (5. Encode to HLS format)
    ↓ (6. Upload segments to S3)
    ↓ (7. Notify MainBackend via API)
MainBackend
    ↓ (8. Update Video status)
Student Views Video
```

## Setup

### 1. Install Dependencies

```bash
cd EncodingBackend
python -m venv venv

# On Windows
venv\Scripts\activate

# On Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Install FFmpeg

**Windows**:
```powershell
choco install ffmpeg
# or download from https://ffmpeg.org/download.html
```

**Mac**:
```bash
brew install ffmpeg
```

**Linux (Ubuntu)**:
```bash
sudo apt-get install ffmpeg
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=1

# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_S3_REGION_NAME=us-east-1
AWS_STORAGE_BUCKET_NAME=your_bucket

# Main Backend
MAIN_BACKEND_URL=http://localhost:8000/api

# FFmpeg
FFMPEG_PATH=ffmpeg
TEMP_VIDEOS_DIR=/tmp/encoding_videos
```

### 4. Initialize Database

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

## Running the Service

### Development

**Terminal 1** - Start Django API server:
```bash
python manage.py runserver 8001
```

**Terminal 2** - Start encoding worker:
```bash
python worker_runner.py
```

### Production

Use Gunicorn for API and run worker as systemd service:

```bash
# API Server
gunicorn config.wsgi:application --bind 0.0.0.0:8001 --workers 4

# Worker (in separate terminal/service)
python worker_runner.py
```

## API Endpoints

### Submit Encoding Job

```bash
POST /api/encoder/jobs/submit_job/
Content-Type: application/json

{
    "video_id": "550e8400-e29b-41d4-a716-446655440000",
    "s3_original_key": "videos/550e8400-e29b-41d4-a716-446655440000/original/video.mp4",
    "s3_hls_folder_key": "videos/550e8400-e29b-41d4-a716-446655440000/hls",
    "input_file_size": 104857600,
    "duration": 300.5,
    "quality_presets": ["720p", "480p", "360p"]
}
```

Response:
```json
{
    "id": "660f9511-f40d-52e5-b827-557755551111",
    "video_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "progress_percentage": 0,
    "created_at": "2025-12-20T10:30:00Z"
}
```

### Get Job Status

```bash
GET /api/encoder/jobs/{job_id}/
```

### Get Queue Status

```bash
GET /api/encoder/jobs/queue_status/
```

Response:
```json
{
    "pending_jobs": 5,
    "processing_jobs": 1,
    "completed_jobs": 24,
    "failed_jobs": 2,
    "total_jobs": 32
}
```

### Update Job Progress (Worker)

```bash
POST /api/encoder/jobs/{job_id}/log_progress/

{
    "progress_percentage": 45,
    "message": "Encoding 720p variant..."
}
```

### Mark Job Completed (Worker)

```bash
POST /api/encoder/jobs/{job_id}/mark_completed/

{
    "output_file_size": 52428800
}
```

### Mark Job Failed (Worker)

```bash
POST /api/encoder/jobs/{job_id}/mark_failed/

{
    "error_message": "FFmpeg timeout after 3600 seconds"
}
```

## Monitoring

### Django Admin

Visit `http://localhost:8001/admin/` to:
- View encoding jobs
- Monitor progress
- Review logs
- Track failures

### Logs

Check logs in:
- Console output
- Django admin (EncodingLog model)
- System logs (if running as service)

### Queue Status

```bash
# Check pending jobs
curl http://localhost:8001/api/encoder/jobs/queue_status/
```

## Scaling

### Multiple Workers

For higher throughput, run multiple worker instances:

```bash
# Terminal 1
WORKER_ID=worker-1 python worker_runner.py

# Terminal 2
WORKER_ID=worker-2 python worker_runner.py

# Terminal 3
WORKER_ID=worker-3 python worker_runner.py
```

Each worker independently polls Redis and processes jobs.

### Worker Configuration

Edit `.env`:
```bash
ENCODING_WORKERS=4          # Number of worker processes
POLL_INTERVAL=5             # Seconds between queue checks
FFMPEG_PATH=ffmpeg          # FFmpeg binary path
TEMP_VIDEOS_DIR=/tmp/videos # Temporary storage
```

## Troubleshooting

### FFmpeg Not Found

```bash
# Check if FFmpeg is installed
ffmpeg -version

# If not, install it
# Windows: choco install ffmpeg
# Mac: brew install ffmpeg
# Linux: sudo apt-get install ffmpeg

# Update FFMPEG_PATH in .env if needed
FFMPEG_PATH=/usr/bin/ffmpeg
```

### Redis Connection Error

```bash
# Check Redis is running
redis-cli ping

# If not installed, install it
# Windows: https://github.com/microsoftarchive/redis/releases
# Mac: brew install redis
# Linux: sudo apt-get install redis-server
```

### Video Encoding Fails

1. Check EncodingLog in Django admin
2. Verify S3 access keys and bucket permissions
3. Ensure temp directory exists and is writable
4. Check FFmpeg version compatibility

### Workers Not Processing Jobs

1. Check `MAIN_BACKEND_URL` points to correct backend
2. Verify Redis connection with `redis-cli KEYS *`
3. Check worker process is running
4. Review worker console output for errors

## Performance Tuning

### Encoding Speed

Adjust FFmpeg presets in `encoder/worker.py`:

```python
# Faster encoding (lower quality)
'720p': {
    'preset': 'ultrafast',
    'bitrate': '2500k',
}

# Better quality (slower)
'720p': {
    'preset': 'slow',
    'bitrate': '2500k',
}
```

### Quality Presets

Edit `.env`:
```bash
VIDEO_QUALITY_PRESETS=1080p,720p,480p,360p,240p
```

## Security

### In Production

1. **Use PostgreSQL** instead of SQLite
2. **Set Django SECRET_KEY** environment variable
3. **Enable HTTPS** between services
4. **Secure Redis** with password
5. **Restrict API access** with API keys
6. **Use IAM roles** instead of AWS keys (if on AWS)
7. **Monitor logs** for errors and attacks
8. **Set proper file permissions** on temp directory

### API Key Authentication

Update `encoder/views.py` to add authentication:

```python
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

class EncodingJobViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["python", "worker_runner.py"]
```

Build and run:
```bash
docker build -t encoding-backend .
docker run -e REDIS_HOST=redis -e AWS_ACCESS_KEY_ID=xxx encoding-backend
```

### Systemd Service (Linux)

Create `/etc/systemd/system/encoding-backend.service`:

```ini
[Unit]
Description=Lebanon Academy Encoding Backend
After=network.target redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/encoding-backend
Environment="PATH=/opt/encoding-backend/venv/bin"
ExecStart=/opt/encoding-backend/venv/bin/python worker_runner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable encoding-backend
sudo systemctl start encoding-backend
sudo systemctl status encoding-backend
```

## Support & Resources

- FFmpeg Documentation: https://ffmpeg.org/documentation.html
- HLS Specification: https://tools.ietf.org/html/rfc8216
- Django REST Framework: https://www.django-rest-framework.org/
- Redis Documentation: https://redis.io/documentation

---

**Version**: 1.0
**Last Updated**: December 20, 2025
