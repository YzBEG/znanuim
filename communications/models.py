import re

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import models
from django.utils import timezone


class LeadRequest(models.Model):
    """Заявка с главной страницы"""
    GOAL_CHOICES = [
        ('grades', 'Подтянуть успеваемость'),
        ('exam', 'Подготовка к ЕГЭ/ОГЭ'),
        ('self', 'Для себя'),
    ]
    
    STATUS_CHOICES = [
        ('new', 'Новая'),
        ('in_progress', 'В обработке'),
        ('contacted', 'Связались'),
        ('closed', 'Закрыта'),
    ]
    
    name = models.CharField(max_length=100, verbose_name='Имя')
    phone = models.CharField(max_length=20, verbose_name='Телефон')
    subject = models.CharField(max_length=100, verbose_name='Предмет')
    goal = models.CharField(max_length=20, choices=GOAL_CHOICES, verbose_name='Цель')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='Статус')
    notes = models.TextField(blank=True, verbose_name='Заметки менеджера')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
    
    def __str__(self):
        return f"Заявка #{self.id} - {self.name} ({self.subject})"


class Conversation(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_conversations")
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_conversations")
    is_paid_relationship = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "tutor")

    def __str__(self):
        return f"Чат {self.student} <-> {self.tutor}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField(blank=True)
    attachment = models.FileField(upload_to="chat/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    SPAM_PATTERNS = [
        r"t\.me",
        r"telegram",
        r"whatsapp",
        r"zoom",
        r"skype",
        r"https?://",
    ]

    def has_forbidden_content(self):
        if self.conversation.is_paid_relationship:
            return False
        lowered = (self.text or "").lower()
        return any(re.search(pattern, lowered) for pattern in self.SPAM_PATTERNS)

    def __str__(self):
        return f"Сообщение #{self.id} от {self.sender}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        LESSON = "lesson", "Урок"
        MESSAGE = "message", "Сообщение"
        SYSTEM = "system", "Система"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"

    def __str__(self):
        return f"{self.title} -> {self.recipient}"

    def as_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "is_read": self.is_read,
            "created_at": timezone.localtime(self.created_at).strftime("%d.%m.%Y %H:%M"),
        }


def create_notification(recipient, title, body="", url="", kind=Notification.Kind.SYSTEM):
    notification = Notification.objects.create(
        recipient=recipient,
        title=title,
        body=body,
        url=url,
        kind=kind,
    )

    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            f"notifications_{recipient.id}",
            {
                "type": "notification_created",
                "notification": notification.as_dict(),
                "unread_count": Notification.objects.filter(
                    recipient=recipient,
                    is_read=False,
                ).count(),
            },
        )

    return notification
