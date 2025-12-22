import uuid
from django.db import models


class EncodingJob(models.Model):
    """
    Tracks encoding jobs for videos
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video_id = models.UUIDField()  # Reference to main backend Video ID
    s3_original_key = models.CharField(max_length=500)  # Path to original video in S3
    s3_hls_folder_key = models.CharField(max_length=500)  # Path to HLS folder in S3
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Encoding details
    input_file_size = models.BigIntegerField()  # Size in bytes
    output_file_size = models.BigIntegerField(null=True, blank=True)
    duration = models.FloatField()  # Video duration in seconds
    
    # Progress tracking
    progress_percentage = models.IntegerField(default=0)
    current_bitrate = models.CharField(max_length=50, null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['video_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"EncodingJob {self.id} - {self.status}"

    def is_retryable(self):
        return self.retry_count < self.max_retries


class EncodingLog(models.Model):
    """
    Logs encoding process for debugging
    """
    LOG_LEVEL_CHOICES = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('DEBUG', 'Debug'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(EncodingJob, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=10, choices=LOG_LEVEL_CHOICES, default='INFO')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.level}] {self.job.id}: {self.message[:50]}"
