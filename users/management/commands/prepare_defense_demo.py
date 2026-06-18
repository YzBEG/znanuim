from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import shutil

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from communications.models import Conversation, LeadRequest, Message, Notification
from lessons.models import AvailabilitySlot, Dispute, LessonMaterial, LessonOrder, LessonSession
from payments.models import Transaction, Wallet, WithdrawalRequest
from reviews.models import Review
from tutors.models import ProfileView, Subject, TutorProfile
from users.models import StudentProfile, User


DEFAULT_PASSWORD = "Znanium2026!"
STUDENT_PASSWORD = "R2atlhCipa"


class Command(BaseCommand):
    help = "Prepare clean defense demo data: 10 tutors, one student, realistic reviews."

    def handle(self, *args, **options):
        with transaction.atomic():
            self.clear_demo_data()
            admin = self.ensure_admin()
            student = self.create_student()
            subjects = self.create_subjects()
            tutors = self.create_tutors(subjects)
            self.create_reviews(student, tutors)
            self.create_future_slots(tutors)
            self.recalculate_review_stats(tutors)
            Wallet.objects.update_or_create(user=admin, defaults={"balance": Decimal("0.00")})

        self.stdout.write(self.style.SUCCESS("Defense demo data prepared."))
        self.stdout.write("Student: anton_dergunov / R2atlhCipa")
        self.stdout.write("Tutors: usernames are listed in the source data, password for all is Znanium2026!")
        self.stdout.write("Catalog tutors: 10")
        self.stdout.write(f"Reviews: {Review.objects.count()}")

    def clear_demo_data(self):
        LessonMaterial.objects.all().delete()
        Dispute.objects.all().delete()
        Review.objects.all().delete()
        LessonSession.objects.all().delete()
        LessonOrder.objects.all().delete()
        AvailabilitySlot.objects.all().delete()
        Message.objects.all().delete()
        Conversation.objects.all().delete()
        Notification.objects.all().delete()
        LeadRequest.objects.all().delete()
        ProfileView.objects.all().delete()
        WithdrawalRequest.objects.all().delete()
        Transaction.objects.all().delete()
        Wallet.objects.exclude(user__role=User.Roles.ADMIN).delete()
        TutorProfile.objects.all().delete()
        StudentProfile.objects.all().delete()
        User.objects.filter(role__in=[User.Roles.STUDENT, User.Roles.TUTOR]).delete()

    def ensure_admin(self):
        admin, _ = User.objects.update_or_create(
            username="admin",
            defaults={
                "role": User.Roles.ADMIN,
                "first_name": "Администратор",
                "last_name": "Znanium",
                "email": "admin@znanium.local",
                "phone": "+79000000000",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "personal_data_consent": True,
                "personal_data_consent_at": timezone.now(),
            },
        )
        admin.set_password(DEFAULT_PASSWORD)
        admin.save(update_fields=["password"])
        return admin

    def create_student(self):
        student = User.objects.create_user(
            username="anton_dergunov",
            password=STUDENT_PASSWORD,
            role=User.Roles.STUDENT,
            first_name="Антон",
            last_name="Дергунов",
            email="ant.dergunov@yandex.ru",
            phone="+79020016881",
            is_active=True,
            personal_data_consent=True,
            personal_data_consent_at=timezone.now(),
        )
        StudentProfile.objects.create(
            user=student,
            class_level="Студент",
            learning_goal="Без описания",
        )
        Wallet.objects.create(user=student, balance=Decimal("25000.00"))
        return student

    def create_subjects(self):
        subject_data = [
            ("Английский язык", "fa-language", "#74b4d9"),
            ("Математика", "fa-calculator", "#10367d"),
            ("Информатика", "fa-code", "#74b4d9"),
            ("Русский язык", "fa-book-open", "#10367d"),
            ("Литература", "fa-book", "#74b4d9"),
            ("Физика", "fa-atom", "#10367d"),
            ("История", "fa-landmark", "#74b4d9"),
            ("Обществознание", "fa-users", "#10367d"),
            ("Биология", "fa-dna", "#74b4d9"),
            ("Химия", "fa-flask", "#10367d"),
            ("Начальная школа", "fa-pencil", "#74b4d9"),
            ("Немецкий язык", "fa-comments", "#10367d"),
            ("Подготовка к ЕГЭ", "fa-graduation-cap", "#74b4d9"),
            ("Подготовка к ОГЭ", "fa-list-check", "#10367d"),
        ]
        subjects = {}
        for name, icon, color in subject_data:
            subject, _ = Subject.objects.update_or_create(
                name=name,
                parent=None,
                defaults={"icon": icon, "color": color},
            )
            subjects[name] = subject
        return subjects

    def create_tutors(self, subjects):
        data = [
            {
                "username": "daria_nikolkina",
                "first_name": "Дарья",
                "last_name": "Николькина",
                "email": "daria.nikolkina@znanium.local",
                "phone": "+79021110001",
                "price": "1000.00",
                "experience": 4,
                "subjects": ["Английский язык", "Подготовка к ЕГЭ"],
                "bio": "Помогаю уверенно говорить на английском, разбираться в грамматике и готовиться к школьным экзаменам без перегруза.",
                "photo_color": "#74b4d9",
                "pro": True,
            },
            {
                "username": "dmitry_solovev",
                "first_name": "Дмитрий",
                "last_name": "Соловьёв",
                "email": "dmitry.solovev@znanium.local",
                "phone": "+79021110002",
                "price": "2000.00",
                "experience": 6,
                "subjects": ["Математика", "Подготовка к ЕГЭ"],
                "bio": "Готовлю школьников к ОГЭ и ЕГЭ по математике, помогаю закрыть пробелы и выстроить понятный план подготовки.",
                "photo_color": "#10367d",
                "pro": True,
            },
            {
                "username": "maxim_romanov",
                "first_name": "Максим",
                "last_name": "Романов",
                "email": "maxim.romanov@znanium.local",
                "phone": "+79021110003",
                "price": "1800.00",
                "experience": 4,
                "subjects": ["Информатика", "Подготовка к ЕГЭ"],
                "bio": "Объясняю программирование, Python, основы алгоритмов и задачи из школьной информатики.",
                "photo_color": "#245a9f",
                "pro": False,
            },
            {
                "username": "elena_vasileva",
                "first_name": "Елена",
                "last_name": "Васильева",
                "email": "elena.vasileva@znanium.local",
                "phone": "+79021110004",
                "price": "1400.00",
                "experience": 8,
                "subjects": ["Русский язык", "Литература", "Подготовка к ОГЭ"],
                "bio": "Готовлю к ОГЭ и ЕГЭ по русскому языку, помогаю разобраться в орфографии, пунктуации и структуре сочинения.",
                "photo_color": "#5f8fc7",
                "pro": False,
            },
            {
                "username": "alexandra_orlova",
                "first_name": "Александра",
                "last_name": "Орлова",
                "email": "alexandra.orlova@znanium.local",
                "phone": "+79021110005",
                "price": "1600.00",
                "experience": 5,
                "subjects": ["Английский язык", "Немецкий язык"],
                "bio": "Помогаю заговорить увереннее, подтянуть грамматику и подготовиться к контрольным работам.",
                "photo_color": "#91c9e4",
                "pro": False,
            },
            {
                "username": "anna_kirillova",
                "first_name": "Анна",
                "last_name": "Кириллова",
                "email": "anna.kirillova@znanium.local",
                "phone": "+79021110006",
                "price": "1200.00",
                "experience": 3,
                "subjects": ["Математика", "Начальная школа"],
                "bio": "Занимаюсь с учениками 5-8 классов, объясняю темы простым языком и помогаю перестать бояться задач.",
                "photo_color": "#74b4d9",
                "pro": False,
            },
            {
                "username": "alexander_volkov",
                "first_name": "Александр",
                "last_name": "Волков",
                "email": "alexander.volkov@znanium.local",
                "phone": "+79021110007",
                "price": "1400.00",
                "experience": 7,
                "subjects": ["История", "Обществознание"],
                "bio": "Помогаю системно готовиться к экзаменам, разбирать даты, термины и причинно-следственные связи.",
                "photo_color": "#10367d",
                "pro": False,
            },
            {
                "username": "maria_smirnova",
                "first_name": "Мария",
                "last_name": "Смирнова",
                "email": "maria.smirnova@znanium.local",
                "phone": "+79021110008",
                "price": "1300.00",
                "experience": 5,
                "subjects": ["Биология", "Химия"],
                "bio": "Разбираю сложные темы по биологии и химии через понятные схемы, примеры и короткие домашние задания.",
                "photo_color": "#5f8fc7",
                "pro": False,
            },
            {
                "username": "ilya_kuznetsov",
                "first_name": "Илья",
                "last_name": "Кузнецов",
                "email": "ilya.kuznetsov@znanium.local",
                "phone": "+79021110009",
                "price": "1700.00",
                "experience": 6,
                "subjects": ["Физика", "Подготовка к ЕГЭ"],
                "bio": "Готовлю к экзаменам по физике, помогаю понять формулы через задачи и реальные примеры.",
                "photo_color": "#245a9f",
                "pro": False,
            },
            {
                "username": "olga_petrova",
                "first_name": "Ольга",
                "last_name": "Петрова",
                "email": "olga.petrova@znanium.local",
                "phone": "+79021110010",
                "price": "1100.00",
                "experience": 9,
                "subjects": ["Начальная школа", "Русский язык"],
                "bio": "Помогаю младшим школьникам читать увереннее, аккуратно писать и спокойно выполнять домашние задания.",
                "photo_color": "#91c9e4",
                "pro": False,
            },
        ]

        created = []
        for item in data:
            user = User.objects.create_user(
                username=item["username"],
                password=DEFAULT_PASSWORD,
                role=User.Roles.TUTOR,
                first_name=item["first_name"],
                last_name=item["last_name"],
                email=item["email"],
                phone=item["phone"],
                is_active=True,
                personal_data_consent=True,
                personal_data_consent_at=timezone.now(),
            )
            Wallet.objects.create(user=user, balance=Decimal("0.00"))
            photo_name = self.ensure_svg_photo(
                username=item["username"],
                initials=f"{item['first_name'][0]}{item['last_name'][0]}",
                color=item["photo_color"],
            )
            profile = TutorProfile.objects.create(
                user=user,
                bio=item["bio"],
                experience_years=item["experience"],
                price_per_hour=Decimal(item["price"]),
                lesson_format=TutorProfile.LessonFormat.ONLINE,
                city="",
                verification_status=TutorProfile.VerificationStatus.APPROVED,
                identity_verified=True,
                photo_file=photo_name,
            )
            profile.subjects.set([subjects[name] for name in item["subjects"]])
            Transaction.objects.create(
                user=user,
                amount=Decimal("200.00"),
                type=Transaction.Type.LISTING_FEE,
                external_payment_id=f"defense-listing-{user.username}",
            )
            if item["pro"]:
                Transaction.objects.create(
                    user=user,
                    amount=Decimal("990.00"),
                    type=Transaction.Type.PRO_SUBSCRIPTION,
                    external_payment_id=f"defense-pro-{user.username}",
                )
            created.append(profile)
        return created

    def ensure_svg_photo(self, username, initials, color):
        seed_dir = settings.BASE_DIR / "static" / "seed" / "tutor_photos"
        for extension in ("jpg", "jpeg", "png", "webp"):
            source = seed_dir / f"{username}.{extension}"
            if source.exists():
                relative_name = f"tutors/photos/{username}.{extension}"
                target = Path(settings.MEDIA_ROOT) / relative_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                return relative_name

        relative_name = f"tutors/photos/{username}.svg"
        target = Path(settings.MEDIA_ROOT) / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        safe_initials = initials.upper()
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">
  <rect width="240" height="240" rx="56" fill="#d7eef8"/>
  <circle cx="120" cy="105" r="72" fill="{color}"/>
  <circle cx="96" cy="88" r="9" fill="#ffffff"/>
  <circle cx="144" cy="88" r="9" fill="#ffffff"/>
  <path d="M88 125c18 18 46 18 64 0" fill="none" stroke="#ffffff" stroke-width="10" stroke-linecap="round"/>
  <text x="120" y="214" text-anchor="middle" font-family="Arial, sans-serif" font-size="38" font-weight="700" fill="#10367d">{safe_initials}</text>
</svg>
"""
        target.write_text(svg, encoding="utf-8")
        return relative_name

    def create_reviews(self, student, tutors):
        review_texts = {
            "daria_nikolkina": [
                (5, "Дарья спокойно объяснила времена и дала понятные упражнения. После занятия стало легче говорить без долгих пауз."),
                (5, "Понравилось, что урок был по делу: разобрали ошибки в грамматике и составили план подготовки."),
            ],
            "dmitry_solovev": [
                (5, "Дмитрий объясняет математику простыми шагами. После занятия я наконец понял, где ошибался в задачах."),
                (5, "Хороший темп урока, много практики и понятные домашние задания."),
            ],
            "maxim_romanov": [
                (5, "Максим помог разобраться с Python и задачами на алгоритмы. Объяснение было понятным и без лишней теории."),
            ],
            "elena_vasileva": [
                (4, "Елена подробно разобрала сочинение и показала, как исправлять типичные ошибки."),
            ],
            "alexandra_orlova": [
                (5, "Занятие прошло легко, много говорили на английском. Получил полезные фразы для практики."),
            ],
            "anna_kirillova": [
                (5, "Анна очень понятно объясняет математику. Ребёнок стал увереннее решать задачи самостоятельно."),
            ],
            "alexander_volkov": [
                (4, "Хорошо разобрали тему по обществознанию, стало проще запоминать определения."),
            ],
            "maria_smirnova": [
                (5, "Мария объяснила сложную тему по биологии через схемы. Материал стал намного понятнее."),
            ],
            "ilya_kuznetsov": [
                (5, "Илья показал, как подходить к задачам по физике. Формулы перестали казаться набором символов."),
            ],
            "olga_petrova": [
                (5, "Ольга нашла подход к ребёнку и помогла спокойно разобрать домашнее задание."),
            ],
        }

        now = timezone.now()
        for tutor_index, profile in enumerate(tutors):
            texts = review_texts.get(profile.user.username, [])
            for review_index, (score, text) in enumerate(texts):
                start_at = now - timedelta(days=30 + tutor_index * 2 + review_index, hours=2)
                slot = AvailabilitySlot.objects.create(
                    tutor=profile,
                    start_at=start_at,
                    end_at=start_at + timedelta(hours=1),
                    is_booked=True,
                )
                order = LessonOrder.objects.create(
                    student=student,
                    tutor=profile.user,
                    slot=slot,
                    price=profile.price_per_hour,
                    status=LessonOrder.Status.COMPLETED,
                    tutor_completed_at=slot.end_at,
                    student_confirmed_at=slot.end_at + timedelta(minutes=10),
                )
                LessonSession.objects.create(
                    order=order,
                    room_name=f"defense-review-{order.id}",
                    meeting_url="https://telemost.yandex.ru/",
                    started_at=slot.start_at,
                    ended_at=slot.end_at,
                )
                Review.objects.create(
                    order=order,
                    student=student,
                    tutor=profile.user,
                    score=score,
                    text=text,
                )

    def create_future_slots(self, tutors):
        base = (timezone.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
        for index, profile in enumerate(tutors):
            day = base + timedelta(days=index % 5)
            for shift in range(2):
                start_at = day + timedelta(hours=shift * 2)
                AvailabilitySlot.objects.create(
                    tutor=profile,
                    start_at=start_at,
                    end_at=start_at + timedelta(hours=1),
                    is_booked=False,
                )

    def recalculate_review_stats(self, tutors):
        for profile in tutors:
            reviews = Review.objects.filter(tutor=profile.user)
            aggregate = reviews.aggregate(avg=Avg("score"))
            profile.rating = Decimal(str(round(aggregate["avg"] or 0, 2)))
            profile.review_count = reviews.count()
            profile.save(update_fields=["rating", "review_count"])
