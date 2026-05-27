from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Roles(models.TextChoices):
        STUDENT = "student", "Ученик"
        TUTOR = "tutor", "Репетитор"
        MODERATOR = "moderator", "Модератор"
        ADMIN = "admin", "Администратор"

    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.STUDENT)
    phone = models.CharField(max_length=20, blank=True)
    email_verified = models.BooleanField(default=False)
    sms_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    class_level = models.CharField(max_length=30, blank=True, help_text="Например: 9 класс")
    learning_goal = models.TextField(blank=True)

    def __str__(self):
        return f"Профиль ученика: {self.user}"
