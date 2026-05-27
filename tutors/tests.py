from decimal import Decimal

from django.test import TestCase

from users.models import User

from .models import TutorProfile


class PublicTutorPageTests(TestCase):
    def setUp(self):
        self.tutor_user = User.objects.create_user(
            username='tutor',
            password='test12345',
            role=User.Roles.TUTOR,
            first_name='Tutor',
            last_name='One',
        )
        self.tutor_profile = TutorProfile.objects.create(
            user=self.tutor_user,
            bio='Algebra and exam prep',
            experience_years=4,
            price_per_hour=Decimal('1300.00'),
            verification_status=TutorProfile.VerificationStatus.APPROVED,
        )

    def test_home_page_renders(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)

    def test_catalog_page_renders(self):
        response = self.client.get('/catalog/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tutor')

    def test_tutor_detail_page_renders(self):
        response = self.client.get(f'/tutors/{self.tutor_profile.id}/')

        self.assertEqual(response.status_code, 200)
