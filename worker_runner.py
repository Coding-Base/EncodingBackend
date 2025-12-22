#!/usr/bin/env python
"""
Standalone worker runner for encoding backend
Run this script to start the video encoding worker
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import and run worker
from encoder.worker import run_worker

if __name__ == '__main__':
    try:
        run_worker()
    except KeyboardInterrupt:
        print("\n✓ Worker stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Worker error: {e}")
        sys.exit(1)
