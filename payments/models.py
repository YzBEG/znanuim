from django.conf import settings
from django.db import models

from lessons.models import LessonOrder


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"Кошелёк {self.user}"


class Transaction(models.Model):
    class Type(models.TextChoices):
        TOP_UP = "top_up", "Пополнение баланса"
        LESSON_PAYMENT = "lesson_payment", "Оплата урока"
        HOLD = "hold", "Резервирование средств"
        RELEASE = "release", "Зачисление репетитору"
        PAYOUT = "payout", "Выплата репетитору"
        REFUND = "refund", "Возврат ученику"
        COMMISSION = "commission", "Комиссия платформы"
        LISTING_FEE = "listing_fee", "Размещение анкеты"
        PRO_SUBSCRIPTION = "pro_subscription", "Подписка Znanium Pro"

    order = models.ForeignKey(LessonOrder, on_delete=models.CASCADE, related_name="transactions", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=20, choices=Type.choices)
    external_payment_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} ({self.user})"


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"
        PAID = "paid", "Выплачено"

    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawal_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requisites = models.CharField(max_length=255)
    tax_receipt_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Вывод #{self.id}: {self.amount} ({self.get_status_display()})"
