import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import StudentProfile, User
from tutors.models import TutorProfile


class PersonalDataConsentMixin:
    personal_data_consent = forms.BooleanField(
        required=True,
        label="Согласие на обработку персональных данных",
        error_messages={
            "required": "Для регистрации нужно согласиться на обработку персональных данных.",
        },
    )


class StudentRegistrationForm(PersonalDataConsentMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True, label="Имя")
    last_name = forms.CharField(max_length=30, required=True, label="Фамилия")
    phone = forms.CharField(max_length=20, required=False, label="Телефон")
    class_level = forms.CharField(max_length=40, required=False, label="Уровень обучения")
    learning_goal = forms.CharField(widget=forms.Textarea, required=False, label="Цель обучения")

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "password1",
            "password2",
            "personal_data_consent",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Например: dasha2017",
            "email": "example@mail.ru",
            "first_name": "Дарья",
            "last_name": "Дергунова",
            "phone": "+7 900 000-00-00",
            "class_level": "9 класс, студент, взрослый",
            "learning_goal": "Например: подготовка к ЕГЭ, подтянуть математику, английский для себя",
            "password1": "Минимум 8 символов",
            "password2": "Повторите пароль",
        }
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)
        self.fields["learning_goal"].widget.attrs.update({"rows": 4, "maxlength": "500"})

    def clean_first_name(self):
        return validate_person_name(self.cleaned_data["first_name"], "имя")

    def clean_last_name(self):
        return validate_person_name(self.cleaned_data["last_name"], "фамилию")

    def clean_phone(self):
        return validate_phone(self.cleaned_data.get("phone", ""), required=False)

    def clean_class_level(self):
        value = (self.cleaned_data.get("class_level") or "").strip()
        if len(value) > 40:
            raise forms.ValidationError("Укажите уровень обучения короче 40 символов.")
        return value

    def clean_learning_goal(self):
        return (self.cleaned_data.get("learning_goal") or "").strip()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.STUDENT
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.phone = self.cleaned_data.get("phone", "")
        user.personal_data_consent = self.cleaned_data["personal_data_consent"]
        user.personal_data_consent_at = timezone.now()

        if commit:
            user.save()
            StudentProfile.objects.create(
                user=user,
                class_level=self.cleaned_data.get("class_level", ""),
                learning_goal=self.cleaned_data.get("learning_goal", ""),
            )
        return user


class TutorRegistrationForm(PersonalDataConsentMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True, label="Имя")
    last_name = forms.CharField(max_length=30, required=True, label="Фамилия")
    phone = forms.CharField(max_length=20, required=True, label="Телефон")

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "password1",
            "password2",
            "personal_data_consent",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Например: tutor_ivanov",
            "email": "tutor@mail.ru",
            "first_name": "Иван",
            "last_name": "Иванов",
            "phone": "+7 900 000-00-00",
            "password1": "Минимум 8 символов",
            "password2": "Повторите пароль",
        }
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)

    def clean_first_name(self):
        return validate_person_name(self.cleaned_data["first_name"], "имя")

    def clean_last_name(self):
        return validate_person_name(self.cleaned_data["last_name"], "фамилию")

    def clean_phone(self):
        return validate_phone(self.cleaned_data.get("phone", ""), required=True)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.TUTOR
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.phone = self.cleaned_data["phone"]
        user.personal_data_consent = self.cleaned_data["personal_data_consent"]
        user.personal_data_consent_at = timezone.now()

        if commit:
            user.save()
            TutorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "price_per_hour": 1000,
                    "verification_status": TutorProfile.VerificationStatus.PENDING,
                    "lesson_format": TutorProfile.LessonFormat.ONLINE,
                    "city": "",
                },
            )
        return user


def validate_person_name(value, label):
    value = value.strip()
    if len(value) < 2:
        raise forms.ValidationError(f"Укажите {label} полностью.")
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё -]+", value):
        raise forms.ValidationError(f"В поле «{label.capitalize()}» допустимы только буквы, пробел и дефис.")
    return " ".join(value.split())


def validate_phone(value, required):
    value = (value or "").strip()
    if not value:
        if required:
            raise forms.ValidationError("Укажите телефон.")
        return ""

    normalized = re.sub(r"[^\d+]", "", value)
    if normalized.startswith("8") and len(normalized) == 11:
        normalized = "+7" + normalized[1:]
    if not re.fullmatch(r"\+7\d{10}", normalized):
        raise forms.ValidationError("Введите телефон в формате +7 900 000-00-00.")
    return normalized
