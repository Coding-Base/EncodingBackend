from rest_framework import serializers
from .models import EncodingJob, EncodingLog


class EncodingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EncodingLog
        fields = ['id', 'level', 'message', 'timestamp']


class EncodingJobSerializer(serializers.ModelSerializer):
    logs = EncodingLogSerializer(many=True, read_only=True)

    class Meta:
        model = EncodingJob
        fields = [
            'id',
            'video_id',
            's3_original_key',
            's3_hls_folder_key',
            'status',
            'input_file_size',
            'output_file_size',
            'duration',
            'progress_percentage',
            'current_bitrate',
            'error_message',
            'retry_count',
            'created_at',
            'started_at',
            'completed_at',
            'updated_at',
            'logs',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EncodingJobRequestSerializer(serializers.Serializer):
    """
    Serializer for incoming encoding job requests from main backend
    """
    video_id = serializers.UUIDField()
    s3_original_key = serializers.CharField(max_length=500)
    s3_hls_folder_key = serializers.CharField(max_length=500)
    input_file_size = serializers.IntegerField()
    duration = serializers.FloatField()
    quality_presets = serializers.ListField(
        child=serializers.CharField(),
        default=['720p', '480p', '360p']
    )


class EncodingStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer for status updates sent to main backend
    """
    video_id = serializers.UUIDField()
    status = serializers.CharField(max_length=20)
    progress_percentage = serializers.IntegerField()
    error_message = serializers.CharField(required=False, allow_blank=True)
