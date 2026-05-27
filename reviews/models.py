from django.conf import settings
from django.db import models

from lessons.models import LessonOrder


class Review(models.Model):
    order = models.OneToOneField(LessonOrder, on_delete=models.CASCADE, related_name="review")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_left")
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received")
    score = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True)
    tutor_reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Отзыв {self.score}/5 для {self.tutor}"
