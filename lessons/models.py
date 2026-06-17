from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from tutors.models import TutorProfile


class AvailabilitySlot(models.Model):
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="slots")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        ordering = ["start_at"]
        unique_together = ("tutor", "start_at", "end_at")

    def __str__(self):
        return f"{self.tutor} {self.start_at:%d.%m %H:%M}-{self.end_at:%H:%M}"


class LessonOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтверждён"
        AWAITING_STUDENT_CONFIRMATION = "awaiting_student_confirmation", "Ожидает подтверждения ученика"
        COMPLETED = "completed", "Проведён"
        CANCELLED = "cancelled", "Отменён"
        IN_DISPUTE = "in_dispute", "В споре"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_orders")
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_orders")
    slot = models.OneToOneField(AvailabilitySlot, on_delete=models.PROTECT, related_name="order")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDING)
    tutor_completed_at = models.DateTimeField(null=True, blank=True)
    student_confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def auto_release_at(self):
        return self.slot.end_at + timedelta(hours=24)

    def can_auto_release(self):
        return self.status == self.Status.COMPLETED and timezone.now() >= self.auto_release_at

    def __str__(self):
        return f"Заказ #{self.id} ({self.get_status_display()})"


class LessonSession(models.Model):
    order = models.OneToOneField(LessonOrder, on_delete=models.CASCADE, related_name="session")
    room_name = models.CharField(max_length=120, unique=True)
    meeting_url = models.URLField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    tutor_joined_at = models.DateTimeField(null=True, blank=True)
    student_joined_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Сессия урока #{self.order_id}"


class LessonMaterial(models.Model):
    order = models.ForeignKey(LessonOrder, on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="lesson_materials/")
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.title} - урок #{self.order_id}"

    def get_file_icon(self):
        ext = self.file.name.split(".")[-1].lower()
        icons = {
            "pdf": "fa-file-pdf",
            "doc": "fa-file-word",
            "docx": "fa-file-word",
            "xls": "fa-file-excel",
            "xlsx": "fa-file-excel",
            "ppt": "fa-file-powerpoint",
            "pptx": "fa-file-powerpoint",
            "jpg": "fa-file-image",
            "jpeg": "fa-file-image",
            "png": "fa-file-image",
            "gif": "fa-file-image",
            "zip": "fa-file-zipper",
            "rar": "fa-file-zipper",
        }
        return icons.get(ext, "fa-file")


class Dispute(models.Model):
    class Decision(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        REFUND_STUDENT = "refund_student", "Возврат ученику"
        PAY_TUTOR = "pay_tutor", "Выплата репетитору"

    order = models.OneToOneField(LessonOrder, on_delete=models.CASCADE, related_name="dispute")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.TextField()
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Спор по заказу #{self.order_id}"
