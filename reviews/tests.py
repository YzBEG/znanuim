from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from lessons.models import AvailabilitySlot, LessonOrder
from payments.models import Transaction
from tutors.models import TutorProfile
from users.models import User

from .models import Review


class ReviewApiTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student',
            password='test12345',
            role=User.Roles.STUDENT,
            first_name='Student',
            last_name='One',
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
            bio='Math tutor',
            experience_years=5,
            price_per_hour=Decimal('1500.00'),
            verification_status=TutorProfile.VerificationStatus.APPROVED,
        )
        Transaction.objects.create(
            user=self.tutor_user,
            amount=Decimal('200.00'),
            type=Transaction.Type.LISTING_FEE,
        )
        self.slot = AvailabilitySlot.objects.create(
            tutor=self.tutor_profile,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
            is_booked=True,
        )
        self.order = LessonOrder.objects.create(
            student=self.student,
            tutor=self.tutor_user,
            slot=self.slot,
            price=Decimal('1500.00'),
            status=LessonOrder.Status.COMPLETED,
        )
        self.review = Review.objects.create(
            order=self.order,
            student=self.student,
            tutor=self.tutor_user,
            score=5,
            text='Great lesson',
        )

    def test_review_list_serializes_existing_reviews(self):
        response = self.client.get('/api/reviews/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_review = response.data['results'][0]
        self.assertEqual(first_review['id'], self.review.id)
        self.assertEqual(first_review['order'], self.order.id)
        self.assertEqual(first_review['score'], 5)
        self.assertEqual(first_review['tutor'], self.tutor_user.id)

    def test_tutor_reviews_action_uses_review_serializer(self):
        response = self.client.get(f'/api/tutors/{self.tutor_profile.id}/reviews/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.review.id)

    def test_student_can_create_review_for_own_completed_order(self):
        another_slot = AvailabilitySlot.objects.create(
            tutor=self.tutor_profile,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
            is_booked=True,
        )
        another_order = LessonOrder.objects.create(
            student=self.student,
            tutor=self.tutor_user,
            slot=another_slot,
            price=Decimal('1500.00'),
            status=LessonOrder.Status.COMPLETED,
        )

        self.client.force_authenticate(self.student)
        response = self.client.post(
            '/api/reviews/',
            {'order': another_order.id, 'score': 4, 'text': 'Useful lesson'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Review.objects.filter(order=another_order, student=self.student, tutor=self.tutor_user).exists()
        )

    def test_student_cannot_review_someone_elses_order(self):
        other_student = User.objects.create_user(
            username='other',
            password='test12345',
            role=User.Roles.STUDENT,
        )

        self.client.force_authenticate(other_student)
        response = self.client.post(
            '/api/reviews/',
            {'order': self.order.id, 'score': 5, 'text': 'Not my lesson'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
