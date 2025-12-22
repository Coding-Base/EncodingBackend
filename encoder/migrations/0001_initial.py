# Generated migration file
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='EncodingJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('video_id', models.UUIDField()),
                ('s3_original_key', models.CharField(max_length=500)),
                ('s3_hls_folder_key', models.CharField(max_length=500)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('input_file_size', models.BigIntegerField()),
                ('output_file_size', models.BigIntegerField(blank=True, null=True)),
                ('duration', models.FloatField()),
                ('progress_percentage', models.IntegerField(default=0)),
                ('current_bitrate', models.CharField(blank=True, max_length=50, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('retry_count', models.IntegerField(default=0)),
                ('max_retries', models.IntegerField(default=3)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EncodingLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('level', models.CharField(choices=[('INFO', 'Info'), ('WARNING', 'Warning'), ('ERROR', 'Error'), ('DEBUG', 'Debug')], default='INFO', max_length=10)),
                ('message', models.TextField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='encoder.encodingjob')),
            ],
            options={
                'ordering': ['timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='encodingjob',
            index=models.Index(fields=['status'], name='encoder_encoding_status_idx'),
        ),
        migrations.AddIndex(
            model_name='encodingjob',
            index=models.Index(fields=['video_id'], name='encoder_encoding_video_id_idx'),
        ),
        migrations.AddIndex(
            model_name='encodingjob',
            index=models.Index(fields=['created_at'], name='encoder_encoding_created_at_idx'),
        ),
    ]
