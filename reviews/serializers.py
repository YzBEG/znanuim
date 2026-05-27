from rest_framework import serializers
from lessons.models import LessonOrder
from .models import Review
from tutors.serializers import UserSerializer


class ReviewSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=LessonOrder.objects.select_related("tutor"))
    student = UserSerializer(read_only=True)
    tutor = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.SerializerMethodField()
    tutor_name = serializers.SerializerMethodField()
    score = serializers.IntegerField(min_value=1, max_value=5)
    
    class Meta:
        model = Review
        fields = [
            'id', 'order', 'student', 'student_name', 'tutor', 'tutor_name',
            'score', 'text', 'tutor_reply', 'created_at'
        ]
        read_only_fields = ['id', 'student', 'tutor', 'tutor_reply', 'created_at']

    def validate_order(self, order):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if user and user.is_authenticated:
            if order.student_id != user.id:
                raise serializers.ValidationError('Можно оставить отзыв только по своему уроку.')

        if order.status != LessonOrder.Status.COMPLETED:
            raise serializers.ValidationError('Отзыв можно оставить только после завершения урока.')

        if Review.objects.filter(order=order).exists():
            raise serializers.ValidationError('Отзыв по этому уроку уже оставлен.')

        return order
    
    def get_student_name(self, obj):
        return obj.student.get_full_name()
    
    def get_tutor_name(self, obj):
        return obj.tutor.get_full_name()
