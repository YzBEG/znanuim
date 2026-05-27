from django.contrib import admin

from .models import AvailabilitySlot, Dispute, LessonOrder, LessonSession


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ('tutor', 'start_at', 'end_at', 'is_booked')
    list_filter = ('is_booked', 'start_at')
    search_fields = ('tutor__user__username', 'tutor__user__first_name', 'tutor__user__last_name')


@admin.register(LessonOrder)
class LessonOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'tutor', 'status', 'price', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('student__username', 'tutor__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display = ('order', 'room_name', 'started_at', 'ended_at')
    search_fields = ('room_name', 'order__id')


# Временно отключаем Dispute из-за бага с Python 3.14
# @admin.register(Dispute)
# class DisputeAdmin(admin.ModelAdmin):
#     list_display = ('order', 'initiated_by', 'decision', 'created_at', 'resolved_at')
#     list_filter = ('decision', 'created_at')
#     search_fields = ('order__id', 'initiated_by__username')
#     readonly_fields = ('created_at',)
