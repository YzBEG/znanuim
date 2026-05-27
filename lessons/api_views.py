from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AvailabilitySlot, LessonMaterial, LessonOrder
from .serializers import (
    AvailabilitySlotSerializer,
    LessonMaterialSerializer,
    LessonOrderSerializer,
)


class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    """API for tutor availability slots."""

    serializer_class = AvailabilitySlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'tutor':
            return AvailabilitySlot.objects.filter(
                tutor__user=user,
            ).select_related('tutor', 'tutor__user').order_by('start_at')

        return AvailabilitySlot.objects.filter(
            is_booked=False,
            start_at__gte=timezone.now(),
        ).select_related('tutor', 'tutor__user').order_by('start_at')

    def perform_create(self, serializer):
        if self.request.user.role != 'tutor':
            raise PermissionDenied('Only tutors can create availability slots.')

        if not hasattr(self.request.user, 'tutor_profile'):
            raise ValidationError('Create a tutor profile before adding slots.')

        serializer.save(tutor=self.request.user.tutor_profile)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.tutor.user != self.request.user:
            raise PermissionDenied('You can edit only your own slots.')
        if instance.is_booked:
            raise ValidationError('Booked slots cannot be edited.')

        serializer.save()

    def perform_destroy(self, instance):
        if instance.tutor.user != self.request.user:
            raise PermissionDenied('You can delete only your own slots.')

        if instance.is_booked:
            raise ValidationError('Booked slots cannot be deleted.')

        instance.delete()


class LessonOrderViewSet(viewsets.ModelViewSet):
    """API for lesson orders."""

    serializer_class = LessonOrderSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        queryset = LessonOrder.objects.select_related(
            'student', 'tutor', 'slot', 'slot__tutor', 'slot__tutor__user',
        )

        if user.role == 'student':
            return queryset.filter(student=user)
        if user.role == 'tutor':
            return queryset.filter(tutor=user)
        return queryset.none()

    def perform_create(self, serializer):
        if self.request.user.role != 'student':
            raise PermissionDenied('Only students can book lessons.')

        selected_slot = serializer.validated_data['slot']

        with transaction.atomic():
            slot = AvailabilitySlot.objects.select_for_update().select_related(
                'tutor', 'tutor__user',
            ).get(pk=selected_slot.pk)

            if slot.is_booked:
                raise ValidationError('This slot is already booked.')
            if slot.start_at < timezone.now():
                raise ValidationError('Cannot book a slot in the past.')

            serializer.save(
                student=self.request.user,
                tutor=slot.tutor.user,
                slot=slot,
                price=slot.tutor.price_per_hour,
                status=LessonOrder.Status.PENDING,
            )
            slot.is_booked = True
            slot.save(update_fields=['is_booked'])

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        order = self.get_object()

        if request.user != order.tutor:
            return Response(
                {'error': 'Only the tutor can confirm this order.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status != LessonOrder.Status.PENDING:
            return Response(
                {'error': 'This order has already been processed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = LessonOrder.Status.CONFIRMED
        order.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        order = self.get_object()

        if request.user != order.tutor:
            return Response(
                {'error': 'Only the tutor can reject this order.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status != LessonOrder.Status.PENDING:
            return Response(
                {'error': 'This order has already been processed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            slot = AvailabilitySlot.objects.select_for_update().get(pk=order.slot_id)
            slot.is_booked = False
            slot.save(update_fields=['is_booked'])
            order.delete()

        return Response({'message': 'Order rejected.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        order = self.get_object()

        if request.user != order.tutor:
            return Response(
                {'error': 'Only the tutor can complete this lesson.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status != LessonOrder.Status.CONFIRMED:
            return Response(
                {'error': 'Only confirmed lessons can be completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = LessonOrder.Status.COMPLETED
        order.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(order)
        return Response(serializer.data)


class LessonMaterialViewSet(viewsets.ModelViewSet):
    """API for lesson materials."""

    serializer_class = LessonMaterialSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return LessonMaterial.objects.filter(
            Q(order__student=user) | Q(order__tutor=user),
        ).select_related(
            'order', 'order__student', 'order__tutor', 'order__slot', 'uploaded_by',
        ).order_by('-uploaded_at')

    def perform_create(self, serializer):
        order = serializer.validated_data['order']
        if self.request.user not in (order.student, order.tutor):
            raise PermissionDenied('You can upload materials only for your own lessons.')

        serializer.save(uploaded_by=self.request.user)
