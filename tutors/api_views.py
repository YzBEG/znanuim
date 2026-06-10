from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from .models import TutorProfile, Subject
from .serializers import TutorProfileSerializer, TutorProfileListSerializer, SubjectSerializer


class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    """API для предметов"""
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class TutorProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """API для профилей репетиторов"""
    queryset = TutorProfile.objects.filter(
        verification_status='approved'
    ).select_related('user').prefetch_related('subjects')
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['user__first_name', 'user__last_name', 'bio', 'subjects__name']
    ordering_fields = ['price_per_hour', 'rating', 'experience_years', 'created_at']
    ordering = ['-rating']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TutorProfileListSerializer
        return TutorProfileSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        from payments.models import Transaction
        possible_user_ids = Transaction.objects.filter(
            type__in=[Transaction.Type.LISTING_FEE, Transaction.Type.PRO_SUBSCRIPTION],
            amount__gt=0,
        ).values_list("user_id", flat=True).distinct()
        paid_user_ids = [
            user_id
            for user_id in possible_user_ids
            if service_is_active_id(user_id, Transaction.Type.LISTING_FEE)
            or service_is_active_id(user_id, Transaction.Type.PRO_SUBSCRIPTION)
        ]
        queryset = queryset.filter(
            user_id__in=paid_user_ids,
            lesson_format__in=[TutorProfile.LessonFormat.ONLINE, TutorProfile.LessonFormat.BOTH],
        )
        
        # Фильтр по предмету
        subject = self.request.query_params.get('subject')
        if subject:
            queryset = queryset.filter(subjects__name__icontains=subject)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price_per_hour__gte=min_price)
        if max_price:
            queryset = queryset.filter(price_per_hour__lte=max_price)
        
        return queryset.distinct()
    
    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """Получить отзывы репетитора"""
        tutor = self.get_object()
        from reviews.models import Review
        from reviews.serializers import ReviewSerializer
        
        reviews = Review.objects.filter(tutor=tutor.user).select_related('student')
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def available_slots(self, request, pk=None):
        """Получить доступные слоты репетитора"""
        tutor = self.get_object()
        from lessons.models import AvailabilitySlot
        from lessons.serializers import AvailabilitySlotSerializer
        from django.utils import timezone
        
        slots = AvailabilitySlot.objects.filter(
            tutor=tutor,
            is_booked=False,
            start_at__gte=timezone.now()
        ).order_by('start_at')[:20]
        
        serializer = AvailabilitySlotSerializer(slots, many=True)
        return Response(serializer.data)


def service_is_active_id(user_id, transaction_type):
    from django.contrib.auth import get_user_model
    from payments.services import service_is_active

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    return bool(user and service_is_active(user, transaction_type))
