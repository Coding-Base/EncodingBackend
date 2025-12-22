from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import EncodingJob, EncodingLog
from .serializers import (
    EncodingJobSerializer,
    EncodingJobRequestSerializer,
    EncodingStatusUpdateSerializer,
)
from .queue_manager import queue_encoding_job, get_job_status
import logging

logger = logging.getLogger(__name__)


class EncodingJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing encoding jobs
    """
    queryset = EncodingJob.objects.all()
    serializer_class = EncodingJobSerializer

    @action(detail=False, methods=['post'])
    def submit_job(self, request):
        """
        Submit a new video for encoding
        Expected request from main backend with video details
        """
        serializer = EncodingJobRequestSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Create encoding job
                job = EncodingJob.objects.create(
                    video_id=serializer.validated_data['video_id'],
                    s3_original_key=serializer.validated_data['s3_original_key'],
                    s3_hls_folder_key=serializer.validated_data['s3_hls_folder_key'],
                    input_file_size=serializer.validated_data['input_file_size'],
                    duration=serializer.validated_data['duration'],
                    status='pending',
                )

                # Queue the job in Redis
                queue_encoding_job(
                    job_id=str(job.id),
                    video_id=str(job.video_id),
                    s3_original_key=job.s3_original_key,
                    s3_hls_folder_key=job.s3_hls_folder_key,
                    quality_presets=serializer.validated_data.get(
                        'quality_presets',
                        ['720p', '480p', '360p']
                    ),
                )

                # Log the job submission
                EncodingLog.objects.create(
                    job=job,
                    level='INFO',
                    message=f'Encoding job submitted for video {job.video_id}'
                )

                logger.info(f"Encoding job {job.id} queued for video {job.video_id}")

                return Response(
                    EncodingJobSerializer(job).data,
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                logger.error(f"Error submitting encoding job: {str(e)}")
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail='pk', methods=['get'])
    def status(self, request, pk=None):
        """
        Get encoding job status
        """
        try:
            job = self.get_object()
            serializer = self.get_serializer(job)
            return Response(serializer.data)
        except EncodingJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def queue_status(self, request):
        """
        Get Redis queue status (how many jobs pending)
        """
        try:
            queue_stats = get_job_status()
            return Response(queue_stats)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail='pk', methods=['post'])
    def log_progress(self, request, pk=None):
        """
        Update job progress (called by worker)
        """
        try:
            job = self.get_object()
            progress = request.data.get('progress_percentage', 0)
            message = request.data.get('message', '')

            job.progress_percentage = progress
            job.updated_at = timezone.now()
            job.save()

            if message:
                EncodingLog.objects.create(
                    job=job,
                    level='INFO',
                    message=message
                )

            return Response({'status': 'updated'})
        except EncodingJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail='pk', methods=['post'])
    def mark_completed(self, request, pk=None):
        """
        Mark job as completed (called by worker)
        """
        try:
            job = self.get_object()
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.output_file_size = request.data.get('output_file_size', 0)
            job.save()

            EncodingLog.objects.create(
                job=job,
                level='INFO',
                message='Encoding completed successfully'
            )

            logger.info(f"Job {job.id} marked as completed")
            return Response({'status': 'completed'})
        except EncodingJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail='pk', methods=['post'])
    def mark_failed(self, request, pk=None):
        """
        Mark job as failed (called by worker)
        """
        try:
            job = self.get_object()
            error_message = request.data.get('error_message', 'Unknown error')
            
            job.status = 'failed'
            job.error_message = error_message
            job.save()

            EncodingLog.objects.create(
                job=job,
                level='ERROR',
                message=f'Encoding failed: {error_message}'
            )

            logger.error(f"Job {job.id} marked as failed: {error_message}")
            return Response({'status': 'failed'})
        except EncodingJob.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )
