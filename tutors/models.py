from django.conf import settings
from django.db import models


class Subject(models.Model):
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome иконка (например: fa-calculator)")
    color = models.CharField(max_length=7, blank=True, default='#7c3aed', help_text="Цвет в формате HEX")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subsubjects",
    )

    class Meta:
        ordering = ["name"]
        unique_together = ("name", "parent")

    def __str__(self):
        return self.name if not self.parent else f"{self.parent.name} -> {self.name}"


class TutorProfile(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Одобрен"
        REJECTED = "rejected", "Отклонен"

    class LessonFormat(models.TextChoices):
        ONLINE = "online", "Онлайн"
        OFFLINE = "offline", "Очный"
        BOTH = "both", "Очно и онлайн"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_profile")
    bio = models.TextField(blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2)
    lesson_format = models.CharField(max_length=20, choices=LessonFormat.choices, default=LessonFormat.ONLINE)
    city = models.CharField(max_length=120, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )

    diploma = models.FileField(upload_to="tutors/diplomas/", blank=True, null=True)
    intro_video = models.FileField(upload_to="tutors/videos/", blank=True, null=True)
    photo_file = models.FileField(upload_to="tutors/photos/", blank=True, null=True)
    photo = models.URLField(max_length=500, blank=True, help_text="URL фотографии репетитора")
    identity_verified = models.BooleanField(default=False)

    subjects = models.ManyToManyField(Subject, related_name="tutors", blank=True)

    class Meta:
        ordering = ["-rating", "price_per_hour"]

    def __str__(self):
        return f"Репетитор: {self.user.get_full_name() or self.user.username}"

    @property
    def avatar_url(self):
        if self.photo_file:
            try:
                return self.photo_file.url
            except ValueError:
                pass
        return self.photo


class ProfileView(models.Model):
    """Статистика просмотров профиля репетитора"""
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="profile_views")
    viewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-viewed_at"]
    
    def __str__(self):
        return f"Просмотр {self.tutor} в {self.viewed_at}"
