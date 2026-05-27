from rest_framework import serializers

from tutors.serializers import UserSerializer

from .models import AvailabilitySlot, LessonMaterial, LessonOrder


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    tutor_name = serializers.SerializerMethodField()

    class Meta:
        model = AvailabilitySlot
        fields = ['id', 'tutor', 'tutor_name', 'start_at', 'end_at', 'is_booked']
        read_only_fields = ['id', 'tutor', 'is_booked']

    def validate(self, attrs):
        start_at = attrs.get('start_at', getattr(self.instance, 'start_at', None))
        end_at = attrs.get('end_at', getattr(self.instance, 'end_at', None))

        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError('End time must be later than start time.')

        return attrs

    def get_tutor_name(self, obj):
        return obj.tutor.user.get_full_name()


class LessonOrderSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    tutor = UserSerializer(read_only=True)
    slot = AvailabilitySlotSerializer(read_only=True)
    slot_id = serializers.PrimaryKeyRelatedField(
        source='slot',
        queryset=AvailabilitySlot.objects.select_related('tutor', 'tutor__user'),
        write_only=True,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = LessonOrder
        fields = [
            'id', 'student', 'tutor', 'slot', 'slot_id', 'price', 'status',
            'status_display', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'student', 'tutor', 'slot', 'price', 'status',
            'created_at', 'updated_at',
        ]


class LessonMaterialSerializer(serializers.ModelSerializer):
    order = LessonOrderSerializer(read_only=True)
    order_id = serializers.PrimaryKeyRelatedField(
        source='order',
        queryset=LessonOrder.objects.select_related('student', 'tutor', 'slot'),
        write_only=True,
    )
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = LessonMaterial
        fields = [
            'id', 'order', 'order_id', 'title', 'description', 'file',
            'uploaded_by', 'uploaded_at',
        ]
        read_only_fields = ['id', 'order', 'uploaded_by', 'uploaded_at']
