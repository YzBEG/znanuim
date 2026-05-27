from django.contrib import admin

from .models import Subject, TutorProfile, ProfileView


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    search_fields = ("name",)


@admin.register(TutorProfile)
class TutorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "price_per_hour", "rating", "verification_status", "lesson_format")
    list_filter = ("verification_status", "lesson_format", "city")
    search_fields = ("user__username", "user__first_name", "user__last_name", "city")
    filter_horizontal = ("subjects",)


@admin.register(ProfileView)
class ProfileViewAdmin(admin.ModelAdmin):
    list_display = ("tutor", "viewer", "ip_address", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("tutor__user__username", "viewer__username", "ip_address")
    readonly_fields = ("tutor", "viewer", "ip_address", "viewed_at")
