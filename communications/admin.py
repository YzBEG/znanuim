from django.contrib import admin

from .models import Conversation, Message, LeadRequest, Notification


@admin.register(LeadRequest)
class LeadRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'subject', 'goal', 'status', 'created_at')
    list_filter = ('status', 'goal', 'created_at')
    search_fields = ('name', 'phone', 'subject')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('status',)
    
    fieldsets = (
        ('Информация о заявке', {
            'fields': ('name', 'phone', 'subject', 'goal')
        }),
        ('Обработка', {
            'fields': ('status', 'notes')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Временно отключаем из-за бага с Python 3.14
# @admin.register(Conversation)
# class ConversationAdmin(admin.ModelAdmin):
#     list_display = ('id', 'student', 'tutor', 'is_paid_relationship', 'created_at')
#     list_filter = ('is_paid_relationship', 'created_at')
#     search_fields = ('student__username', 'tutor__username')
#     readonly_fields = ('created_at',)


# @admin.register(Message)
# class MessageAdmin(admin.ModelAdmin):
#     list_display = ('id', 'conversation', 'sender', 'created_at')
#     list_filter = ('created_at',)
#     search_fields = ('sender__username', 'text')
#     readonly_fields = ('created_at',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("recipient__username", "recipient__first_name", "recipient__last_name", "title", "body")
    readonly_fields = ("created_at",)

