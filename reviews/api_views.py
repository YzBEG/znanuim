from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from .models import Review
from .content_filter import contains_profanity
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """REST API for lesson reviews."""

    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Review.objects.select_related('student', 'tutor', 'order')

        tutor_id = self.request.query_params.get('tutor')
        if tutor_id:
            queryset = queryset.filter(tutor__id=tutor_id)

        student_id = self.request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(student__id=student_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        if self.request.user.role != 'student':
            raise PermissionDenied('Only students can leave reviews.')

        order = serializer.validated_data['order']
        serializer.save(student=self.request.user, tutor=order.tutor)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        review = self.get_object()

        if request.user != review.tutor:
            return Response(
                {'error': 'Only the reviewed tutor can reply.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        reply_text = (request.data.get('tutor_reply') or '').strip()
        if not reply_text:
            return Response(
                {'error': 'Reply text is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if contains_profanity(reply_text):
            return Response(
                {'error': 'Reply contains forbidden words.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review.tutor_reply = reply_text[:2000]
        review.save(update_fields=['tutor_reply'])

        serializer = self.get_serializer(review)
        return Response(serializer.data)
