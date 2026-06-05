from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Transaction, Wallet


LESSON_COMMISSION_RATE = Decimal("0.12")
TUTOR_LISTING_FEE = Decimal("200.00")
ZNANIUM_PRO_FEE = Decimal("900.00")
DIRECTOR_USERNAME = "director"


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def get_director_user():
    User = get_user_model()
    director, created = User.objects.get_or_create(
        username=DIRECTOR_USERNAME,
        defaults={
            "first_name": "Директор",
            "last_name": "Znanium",
            "email": "director@znanium.local",
            "role": User.Roles.ADMIN,
            "is_staff": True,
        },
    )
    if created:
        director.set_unusable_password()
        director.save(update_fields=["password"])
    get_wallet(director)
    return director


@transaction.atomic
def demo_top_up(user, amount):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Сумма пополнения должна быть больше нуля")

    wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
    wallet.balance = money(wallet.balance + amount)
    wallet.save(update_fields=["balance"])
    Transaction.objects.create(
        user=user,
        amount=amount,
        type=Transaction.Type.TOP_UP,
        external_payment_id="demo-top-up",
    )
    return wallet


@transaction.atomic
def complete_paid_lesson(order):
    if Transaction.objects.filter(order=order, type=Transaction.Type.LESSON_PAYMENT).exists():
        return False

    lesson_price = money(order.price)
    student_wallet = Wallet.objects.select_for_update().get_or_create(user=order.student)[0]
    tutor_wallet = Wallet.objects.select_for_update().get_or_create(user=order.tutor)[0]
    director = get_director_user()
    director_wallet = Wallet.objects.select_for_update().get_or_create(user=director)[0]

    if student_wallet.balance < lesson_price:
        raise ValueError("На балансе ученика недостаточно средств для оплаты урока")

    commission = money(lesson_price * LESSON_COMMISSION_RATE)
    tutor_amount = money(lesson_price - commission)

    student_wallet.balance = money(student_wallet.balance - lesson_price)
    tutor_wallet.balance = money(tutor_wallet.balance + tutor_amount)
    director_wallet.balance = money(director_wallet.balance + commission)
    student_wallet.save(update_fields=["balance"])
    tutor_wallet.save(update_fields=["balance"])
    director_wallet.save(update_fields=["balance"])

    Transaction.objects.create(
        order=order,
        user=order.student,
        amount=lesson_price,
        type=Transaction.Type.LESSON_PAYMENT,
        external_payment_id="demo-lesson-payment",
    )
    Transaction.objects.create(
        order=order,
        user=order.tutor,
        amount=tutor_amount,
        type=Transaction.Type.PAYOUT,
        external_payment_id="demo-tutor-payout",
    )
    Transaction.objects.create(
        order=order,
        user=director,
        amount=commission,
        type=Transaction.Type.COMMISSION,
        external_payment_id="demo-platform-commission",
    )
    return True


@transaction.atomic
def buy_platform_service(user, amount, transaction_type):
    amount = money(amount)
    wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
    director = get_director_user()
    director_wallet = Wallet.objects.select_for_update().get_or_create(user=director)[0]

    if wallet.balance < amount:
        raise ValueError("Недостаточно средств на балансе")

    wallet.balance = money(wallet.balance - amount)
    director_wallet.balance = money(director_wallet.balance + amount)
    wallet.save(update_fields=["balance"])
    director_wallet.save(update_fields=["balance"])

    Transaction.objects.create(
        user=user,
        amount=amount,
        type=transaction_type,
        external_payment_id="demo-platform-service",
    )
    Transaction.objects.create(
        user=director,
        amount=amount,
        type=transaction_type,
        external_payment_id=f"demo-income-from-{user.id}",
    )
    return wallet


def service_paid_until(user, transaction_type):
    last_transaction = Transaction.objects.filter(
        user=user,
        type=transaction_type,
    ).order_by("-created_at").first()
    if not last_transaction:
        return None
    return last_transaction.created_at + timedelta(days=30)


def service_is_active(user, transaction_type):
    paid_until = service_paid_until(user, transaction_type)
    return paid_until is not None and paid_until >= timezone.now()
