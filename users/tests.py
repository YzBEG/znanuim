import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from tutors.models import TutorProfile
from users.models import User


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


class RegistrationConsentTests(TestCase):
    def test_student_registration_requires_personal_data_consent(self):
        response = self.client.post(
            reverse("register_student"),
            {
                "username": "student_without_consent",
                "email": "student@example.com",
                "first_name": "Anna",
                "last_name": "Ivanova",
                "phone": "+79000000000",
                "password1": "StrongPass2026!",
                "password2": "StrongPass2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="student_without_consent").exists())

    def test_tutor_registration_requires_personal_data_consent(self):
        response = self.client.post(
            reverse("register_tutor"),
            {
                "username": "tutor_without_consent",
                "email": "tutor@example.com",
                "first_name": "Ivan",
                "last_name": "Petrov",
                "phone": "+79000000001",
                "password1": "StrongPass2026!",
                "password2": "StrongPass2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="tutor_without_consent").exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class TutorProfileEditTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(
            username='tutor_test',
            password='test12345',
            role=User.Roles.TUTOR,
            first_name='Иван',
            last_name='Иванов',
        )
        self.profile = TutorProfile.objects.create(
            user=self.user,
            bio='Старое описание',
            experience_years=1,
            price_per_hour=Decimal('1000.00'),
        )

    def test_profile_edit_updates_text_fields_and_diploma(self):
        self.client.login(username='tutor_test', password='test12345')

        diploma = SimpleUploadedFile(
            'diploma.pdf',
            b'%PDF-1.4 test diploma',
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('tutor_profile_edit'),
            {
                'first_name': 'Петр',
                'last_name': 'Петров',
                'email': 'petr@example.com',
                'phone': '+79990000000',
                'bio': 'Новое описание',
                'experience_years': '5',
                'price_per_hour': '1500',
                'lesson_format': 'online',
                'city': 'Москва',
                'diploma': diploma,
            },
        )

        self.assertRedirects(response, reverse('tutor_dashboard'))
        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(self.user.first_name, 'Петр')
        self.assertEqual(self.profile.bio, 'Новое описание')
        self.assertEqual(self.profile.experience_years, 5)
        self.assertEqual(self.profile.price_per_hour, Decimal('1500'))
        self.assertTrue(self.profile.diploma.name.startswith('tutors/diplomas/'))
