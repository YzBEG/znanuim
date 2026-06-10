from rest_framework import serializers

from .models import Subject, TutorProfile
from users.models import User


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role"]
        read_only_fields = ["id", "role"]


class TutorProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    subjects = SubjectSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()
    rating_display = serializers.SerializerMethodField()

    class Meta:
        model = TutorProfile
        fields = [
            "id",
            "user",
            "full_name",
            "subjects",
            "bio",
            "experience_years",
            "price_per_hour",
            "lesson_format",
            "diploma",
            "rating",
            "rating_display",
            "review_count",
            "verification_status",
            "identity_verified",
        ]
        read_only_fields = ["id", "rating", "review_count", "verification_status", "identity_verified"]

    def get_full_name(self, obj):
        return obj.user.get_full_name()

    def get_rating_display(self, obj):
        return f"{obj.rating:.1f}" if obj.rating else "Нет оценок"


class TutorProfileListSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    subjects = SubjectSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = TutorProfile
        fields = [
            "id",
            "user",
            "full_name",
            "subjects",
            "bio",
            "experience_years",
            "price_per_hour",
            "lesson_format",
            "rating",
            "review_count",
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name()
