"""
URL Configuration for EncodingBackend service
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/encoder/', include('encoder.urls')),
]
