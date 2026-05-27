from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from tutors.models import TutorProfile
from users.models import User

from .models import AvailabilitySlot, LessonOrder


class LessonApiTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student',
            password='test12345',
            role=User.Roles.STUDENT,
        )
        self.tutor_user = User.objects.create_user(
            username='tutor',
            password='test12345',
            role=User.Roles.TUTOR,
            first_name='Tutor',
            last_name='One',
        )
        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            bio='Physics tutor',
            experience_years=3,
            price_per_hour=Decimal('1200.00'),
            verification_status=TutorProfile.VerificationStatus.APPROVED,
        )
        self.slot = AvailabilitySlot.objects.create(
            tutor=self.tutor_profile,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
        )

    def test_available_slots_action_serializes_nonempty_slot_list(self):
        response = self.client.get(f'/api/tutors/{self.tutor_profile.id}/available_slots/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.slot.id)
        self.assertNotIn('created_at', response.data[0])

    def test_student_can_book_available_slot_via_api(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            '/api/orders/',
            {'slot_id': self.slot.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)
        self.assertTrue(
            LessonOrder.objects.filter(
                student=self.student,
                tutor=self.tutor_user,
                slot=self.slot,
                status=LessonOrder.Status.PENDING,
            ).exists()
        )

    def test_tutor_cannot_book_lesson_via_api(self):
        self.client.force_authenticate(self.tutor_user)
        response = self.client.post(
            '/api/orders/',
            {'slot_id': self.slot.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_booked)
