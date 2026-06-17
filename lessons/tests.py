import shutil
import tempfile
from decimal import Decimal
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from payments.models import Transaction, Wallet
from tutors.models import TutorProfile
from users.models import User

from .models import AvailabilitySlot, LessonMaterial, LessonOrder


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
        Transaction.objects.create(
            user=self.tutor_user,
            amount=Decimal('200.00'),
            type=Transaction.Type.LISTING_FEE,
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


class LessonCompletionPaymentTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student_completion',
            password='test12345',
            role=User.Roles.STUDENT,
        )
        self.tutor_user = User.objects.create_user(
            username='tutor_completion',
            password='test12345',
            role=User.Roles.TUTOR,
            first_name='Tutor',
            last_name='Completion',
        )
        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            bio='Math tutor',
            experience_years=5,
            price_per_hour=Decimal('1200.00'),
            verification_status=TutorProfile.VerificationStatus.APPROVED,
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
            price=Decimal('1200.00'),
            status=LessonOrder.Status.CONFIRMED,
        )
        Wallet.objects.create(user=self.student, balance=Decimal('1500.00'))
        Wallet.objects.create(user=self.tutor_user, balance=Decimal('0.00'))

    def test_tutor_completion_waits_for_student_confirmation_without_payment(self):
        self.client.login(username='tutor_completion', password='test12345')

        response = self.client.get(reverse('complete_lesson', args=[self.order.id]))

        self.assertRedirects(response, reverse('tutor_dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION)
        self.assertIsNotNone(self.order.tutor_completed_at)
        self.assertFalse(
            Transaction.objects.filter(
                order=self.order,
                type=Transaction.Type.LESSON_PAYMENT,
            ).exists()
        )

    def test_student_confirmation_charges_student_and_pays_tutor(self):
        self.order.status = LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION
        self.order.tutor_completed_at = timezone.now()
        self.order.save(update_fields=['status', 'tutor_completed_at'])
        self.client.login(username='student_completion', password='test12345')

        response = self.client.get(reverse('confirm_lesson_completion', args=[self.order.id]))

        self.assertRedirects(response, reverse('student_dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, LessonOrder.Status.COMPLETED)
        self.assertIsNotNone(self.order.student_confirmed_at)
        self.student.wallet.refresh_from_db()
        self.tutor_user.wallet.refresh_from_db()
        owner_wallet = Wallet.objects.get(user__username='admin')
        self.assertEqual(self.student.wallet.balance, Decimal('300.00'))
        self.assertEqual(self.tutor_user.wallet.balance, Decimal('1056.00'))
        self.assertEqual(owner_wallet.balance, Decimal('144.00'))

    def test_student_dispute_does_not_charge_lesson(self):
        self.order.status = LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION
        self.order.tutor_completed_at = timezone.now()
        self.order.save(update_fields=['status', 'tutor_completed_at'])
        self.client.login(username='student_completion', password='test12345')

        response = self.client.post(
            reverse('dispute_lesson_completion', args=[self.order.id]),
            {'reason': 'Ученик не смог подключиться к занятию.'},
        )

        self.assertRedirects(response, reverse('student_dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, LessonOrder.Status.IN_DISPUTE)
        self.student.wallet.refresh_from_db()
        self.tutor_user.wallet.refresh_from_db()
        self.assertEqual(self.student.wallet.balance, Decimal('1500.00'))
        self.assertEqual(self.tutor_user.wallet.balance, Decimal('0.00'))
        self.assertFalse(
            Transaction.objects.filter(
                order=self.order,
                type=Transaction.Type.LESSON_PAYMENT,
            ).exists()
        )


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class LessonMaterialUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.student = User.objects.create_user(
            username='student_materials',
            password='test12345',
            role=User.Roles.STUDENT,
        )
        self.tutor_user = User.objects.create_user(
            username='tutor_materials',
            password='test12345',
            role=User.Roles.TUTOR,
        )
        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            bio='Math tutor',
            experience_years=4,
            price_per_hour=Decimal('1300.00'),
            verification_status=TutorProfile.VerificationStatus.APPROVED,
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
            price=Decimal('1300.00'),
            status=LessonOrder.Status.CONFIRMED,
        )

    def test_tutor_can_upload_lesson_material(self):
        self.client.login(username='tutor_materials', password='test12345')

        material_file = SimpleUploadedFile(
            'lesson.pdf',
            b'%PDF-1.4 lesson material',
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('upload_material', args=[self.order.id]),
            {
                'title': 'Конспект урока',
                'description': 'Материал после занятия',
                'file': material_file,
            },
        )

        self.assertRedirects(response, reverse('lesson_materials', args=[self.order.id]))
        material = LessonMaterial.objects.get(order=self.order)
        self.assertEqual(material.title, 'Конспект урока')
        self.assertEqual(material.uploaded_by, self.tutor_user)
        self.assertTrue(material.file.name.startswith('lesson_materials/'))
