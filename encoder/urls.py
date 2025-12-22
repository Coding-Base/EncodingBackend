from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EncodingJobViewSet

router = DefaultRouter()
router.register(r'jobs', EncodingJobViewSet, basename='encoding-job')

urlpatterns = [
    path('', include(router.urls)),
]
