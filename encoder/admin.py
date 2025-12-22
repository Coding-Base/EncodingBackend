from django.contrib import admin
from .models import EncodingJob, EncodingLog


@admin.register(EncodingJob)
class EncodingJobAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'video_id',
        'status',
        'progress_percentage',
        'created_at',
        'completed_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['video_id', 'id']
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'started_at',
        'completed_at',
    ]

    fieldsets = (
        ('Job Information', {
            'fields': ('id', 'video_id', 'status'),
        }),
        ('S3 Paths', {
            'fields': ('s3_original_key', 's3_hls_folder_key'),
        }),
        ('File Details', {
            'fields': ('input_file_size', 'output_file_size', 'duration'),
        }),
        ('Progress', {
            'fields': ('progress_percentage', 'current_bitrate'),
        }),
        ('Error Handling', {
            'fields': ('error_message', 'retry_count', 'max_retries'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at', 'updated_at'),
        }),
    )

    def has_add_permission(self, request):
        return False


@admin.register(EncodingLog)
class EncodingLogAdmin(admin.ModelAdmin):
    list_display = ['job', 'level', 'message', 'timestamp']
    list_filter = ['level', 'timestamp', 'job']
    search_fields = ['message', 'job__video_id']
    readonly_fields = ['timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
