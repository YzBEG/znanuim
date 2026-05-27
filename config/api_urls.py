"""
API URLs для REST Framework
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Импорт ViewSets
from tutors.api_views import TutorProfileViewSet, SubjectViewSet
from lessons.api_views import AvailabilitySlotViewSet, LessonOrderViewSet, LessonMaterialViewSet
from reviews.api_views import ReviewViewSet
from communications.api_views import LeadRequestViewSet, ConversationViewSet, MessageViewSet

# Создаём router
router = DefaultRouter()

# Регистрируем ViewSets
router.register(r'tutors', TutorProfileViewSet, basename='tutor')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'slots', AvailabilitySlotViewSet, basename='slot')
router.register(r'orders', LessonOrderViewSet, basename='order')
router.register(r'materials', LessonMaterialViewSet, basename='material')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'leads', LeadRequestViewSet, basename='lead')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('rest_framework.urls')),  # Browsable API login/logout
]
