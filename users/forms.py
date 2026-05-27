from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, StudentProfile
from tutors.models import TutorProfile


class StudentRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True, label="Имя")
    last_name = forms.CharField(max_length=30, required=True, label="Фамилия")
    phone = forms.CharField(max_length=20, required=False, label="Телефон")
    class_level = forms.CharField(max_length=30, required=False, label="Класс (если школьник)")
    learning_goal = forms.CharField(widget=forms.Textarea, required=False, label="Цель обучения")

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.STUDENT
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data.get('phone', '')
        
        if commit:
            user.save()
            StudentProfile.objects.create(
                user=user,
                class_level=self.cleaned_data.get('class_level', ''),
                learning_goal=self.cleaned_data.get('learning_goal', '')
            )
        return user


class TutorRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True, label="Имя")
    last_name = forms.CharField(max_length=30, required=True, label="Фамилия")
    phone = forms.CharField(max_length=20, required=True, label="Телефон")

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.TUTOR
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        
        if commit:
            user.save()
            TutorProfile.objects.get_or_create(
                user=user,
                defaults={
                    'price_per_hour': 1000,
                    'verification_status': TutorProfile.VerificationStatus.PENDING,
                },
            )
        return user
