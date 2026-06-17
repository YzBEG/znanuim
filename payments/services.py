from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Transaction, Wallet, WithdrawalRequest


LESSON_COMMISSION_RATE = Decimal("0.12")
TUTOR_LISTING_FEE = Decimal("200.00")
ZNANIUM_PRO_FEE = Decimal("990.00")
PLATFORM_OWNER_USERNAME = "admin"
MAX_TOP_UP_AMOUNT = Decimal("1000000.00")


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def get_platform_owner_user():
    User = get_user_model()
    owner = User.objects.filter(username=PLATFORM_OWNER_USERNAME).first()
    if owner is None:
        owner = User.objects.filter(is_superuser=True).order_by("id").first()
    if owner is None:
        owner = User.objects.create(
            username=PLATFORM_OWNER_USERNAME,
            first_name="Администратор",
            last_name="Znanium",
            email="admin@znanium.local",
            role=User.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        owner.set_unusable_password()
        owner.save(update_fields=["password"])
    get_wallet(owner)
    return owner


@transaction.atomic
def top_up_wallet(user, amount):
    amount = money(amount)
    if amount < Decimal("100.00"):
        raise ValueError("Минимальная сумма пополнения — 100 ₽")
    if amount > MAX_TOP_UP_AMOUNT:
        raise ValueError("Максимальная сумма пополнения за одну операцию — 1 000 000 ₽")

    wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
    wallet.balance = money(wallet.balance + amount)
    wallet.save(update_fields=["balance"])
    Transaction.objects.create(
        user=user,
        amount=amount,
        type=Transaction.Type.TOP_UP,
        external_payment_id="balance-top-up",
    )
    return wallet


@transaction.atomic
def complete_paid_lesson(order):
    if Transaction.objects.filter(order=order, type=Transaction.Type.LESSON_PAYMENT).exists():
        return False

    lesson_price = money(order.price)
    student_wallet = Wallet.objects.select_for_update().get_or_create(user=order.student)[0]
    tutor_wallet = Wallet.objects.select_for_update().get_or_create(user=order.tutor)[0]
    owner = get_platform_owner_user()
    owner_wallet = Wallet.objects.select_for_update().get_or_create(user=owner)[0]

    if student_wallet.balance < lesson_price:
        raise ValueError("На балансе ученика недостаточно средств для оплаты урока")

    commission = money(lesson_price * LESSON_COMMISSION_RATE)
    tutor_amount = money(lesson_price - commission)

    student_wallet.balance = money(student_wallet.balance - lesson_price)
    tutor_wallet.balance = money(tutor_wallet.balance + tutor_amount)
    owner_wallet.balance = money(owner_wallet.balance + commission)
    student_wallet.save(update_fields=["balance"])
    tutor_wallet.save(update_fields=["balance"])
    owner_wallet.save(update_fields=["balance"])

    Transaction.objects.create(
        order=order,
        user=order.student,
        amount=lesson_price,
        type=Transaction.Type.LESSON_PAYMENT,
        external_payment_id="lesson-payment",
    )
    Transaction.objects.create(
        order=order,
        user=order.tutor,
        amount=tutor_amount,
        type=Transaction.Type.PAYOUT,
        external_payment_id="tutor-payout",
    )
    Transaction.objects.create(
        order=order,
        user=owner,
        amount=commission,
        type=Transaction.Type.COMMISSION,
        external_payment_id="platform-commission",
    )
    return True


@transaction.atomic
def buy_platform_service(user, amount, transaction_type):
    amount = money(amount)
    wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
    owner = get_platform_owner_user()
    owner_wallet = Wallet.objects.select_for_update().get_or_create(user=owner)[0]

    if wallet.balance < amount:
        raise ValueError("Недостаточно средств на балансе")

    wallet.balance = money(wallet.balance - amount)
    owner_wallet.balance = money(owner_wallet.balance + amount)
    wallet.save(update_fields=["balance"])
    owner_wallet.save(update_fields=["balance"])

    Transaction.objects.create(
        user=user,
        amount=amount,
        type=transaction_type,
        external_payment_id="platform-service",
    )
    Transaction.objects.create(
        user=owner,
        amount=amount,
        type=transaction_type,
        external_payment_id=f"income-from-{user.id}",
    )
    return wallet


def service_paid_until(user, transaction_type):
    paid_until = None
    transactions = Transaction.objects.filter(
        user=user,
        type=transaction_type,
        amount__gt=0,
    ).order_by("created_at")

    for service_transaction in transactions:
        starts_at = paid_until if paid_until and paid_until > service_transaction.created_at else service_transaction.created_at
        paid_until = starts_at + timedelta(days=30)

    return paid_until


def service_is_active(user, transaction_type):
    paid_until = service_paid_until(user, transaction_type)
    return paid_until is not None and paid_until >= timezone.now()


def tutor_publication_is_active(user):
    """Публикация анкеты активна после оплаты размещения или активной подписки Pro."""
    return service_is_active(user, Transaction.Type.LISTING_FEE) or service_is_active(
        user,
        Transaction.Type.PRO_SUBSCRIPTION,
    )


@transaction.atomic
def create_withdrawal_request(user, amount, requisites):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Сумма вывода должна быть больше нуля")
    if not requisites.strip():
        raise ValueError("Укажите реквизиты для вывода")

    wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
    if wallet.balance < amount:
        raise ValueError("На балансе недостаточно средств для вывода")

    wallet.balance = money(wallet.balance - amount)
    wallet.save(update_fields=["balance"])

    withdrawal = WithdrawalRequest.objects.create(
        tutor=user,
        amount=amount,
        requisites=requisites.strip(),
    )
    Transaction.objects.create(
        user=user,
        amount=-amount,
        type=Transaction.Type.PAYOUT,
        external_payment_id=f"withdrawal-{withdrawal.id}",
    )
    return withdrawal
