from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from lessons.models import AvailabilitySlot, LessonOrder, LessonSession
from payments.models import Wallet
from payments.services import get_director_user
from tutors.models import Subject, TutorProfile
from users.models import StudentProfile, User


class Command(BaseCommand):
    help = "Create demo users, subjects, tutor profiles, slots, and one confirmed lesson."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Znanium2026!",
            help="Password for demo users.",
        )

    def handle(self, *args, **options):
        password = options["password"]

        admin = self.upsert_user(
            username="admin",
            password=password,
            role=User.Roles.ADMIN,
            first_name="Администратор",
            last_name="Системы",
            email="admin@znanium.local",
            is_staff=True,
            is_superuser=True,
        )
        student = self.upsert_user(
            username="YzBEG",
            password=password,
            role=User.Roles.STUDENT,
            first_name="Антон",
            last_name="Дергунов",
            email="student@znanium.local",
        )
        tutor = self.upsert_user(
            username="GUGU",
            password=password,
            role=User.Roles.TUTOR,
            first_name="Дмитрий",
            last_name="Соловьёв",
            email="tutor@znanium.local",
        )
        Wallet.objects.update_or_create(user=student, defaults={"balance": Decimal("5000.00")})
        Wallet.objects.update_or_create(user=tutor, defaults={"balance": Decimal("2000.00")})

        StudentProfile.objects.get_or_create(
            user=student,
            defaults={
                "class_level": "10 класс",
                "learning_goal": "Подготовка к экзаменам и повышение успеваемости.",
            },
        )

        subjects = self.create_subjects()
        profile, _ = TutorProfile.objects.update_or_create(
            user=tutor,
            defaults={
                "bio": (
                    "Преподаватель с опытом индивидуальных онлайн-занятий. "
                    "Помогает системно разобрать сложные темы и подготовиться к экзаменам."
                ),
                "experience_years": 7,
                "price_per_hour": Decimal("1500.00"),
                "lesson_format": TutorProfile.LessonFormat.ONLINE,
                "city": "Москва",
                "rating": Decimal("4.80"),
                "review_count": 6,
                "verification_status": TutorProfile.VerificationStatus.APPROVED,
                "identity_verified": True,
                "photo": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=500&q=80",
            },
        )
        profile.subjects.set(subjects[:3])

        get_director_user()
        self.create_slots_and_order(profile, student, tutor)

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write(f"Admin: admin / {password}")
        self.stdout.write(f"Student: YzBEG / {password}")
        self.stdout.write(f"Tutor: GUGU / {password}")

    def upsert_user(self, username, password, role, **fields):
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "role": role,
                "first_name": fields.get("first_name", ""),
                "last_name": fields.get("last_name", ""),
                "email": fields.get("email", ""),
                "phone": fields.get("phone", "+79990000000"),
                "is_staff": fields.get("is_staff", False),
                "is_superuser": fields.get("is_superuser", False),
                "is_active": True,
            },
        )
        user.set_password(password)
        user.save()
        return user

    def create_subjects(self):
        subject_data = [
            ("Математика", "fa-calculator", "#5b4fd8"),
            ("Физика", "fa-atom", "#2f80ed"),
            ("Английский язык", "fa-language", "#ff5a5f"),
            ("Информатика", "fa-code", "#00b894"),
            ("Русский язык", "fa-book-open", "#ef4444"),
            ("Обществознание", "fa-users", "#f97316"),
        ]
        subjects = []
        for name, icon, color in subject_data:
            subject, _ = Subject.objects.update_or_create(
                name=name,
                parent=None,
                defaults={"icon": icon, "color": color},
            )
            subjects.append(subject)
        return subjects

    def create_slots_and_order(self, profile, student, tutor):
        now = timezone.now()
        slot_times = [
            now + timedelta(days=1, hours=2),
            now + timedelta(days=2, hours=4),
            now + timedelta(days=4, hours=3),
        ]

        first_slot = None
        for start_at in slot_times:
            end_at = start_at + timedelta(hours=1)
            slot, _ = AvailabilitySlot.objects.get_or_create(
                tutor=profile,
                start_at=start_at.replace(minute=0, second=0, microsecond=0),
                end_at=end_at.replace(minute=0, second=0, microsecond=0),
                defaults={"is_booked": False},
            )
            if first_slot is None:
                first_slot = slot

        first_slot.is_booked = True
        first_slot.save(update_fields=["is_booked"])
        order, _ = LessonOrder.objects.update_or_create(
            slot=first_slot,
            defaults={
                "student": student,
                "tutor": tutor,
                "price": profile.price_per_hour,
                "status": LessonOrder.Status.CONFIRMED,
            },
        )
        LessonSession.objects.get_or_create(
            order=order,
            defaults={"room_name": f"lesson-{order.id}"},
        )
