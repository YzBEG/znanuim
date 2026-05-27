from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'tutor', 'score', 'created_at')
    list_filter = ('score', 'created_at')
    search_fields = ('student__username', 'tutor__username', 'text')
    readonly_fields = ('created_at',)
