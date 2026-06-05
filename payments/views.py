from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import Transaction
from .services import (
    TUTOR_LISTING_FEE,
    ZNANIUM_PRO_FEE,
    buy_platform_service,
    demo_top_up,
)


@login_required
def top_up_balance(request):
    if request.method != "POST":
        return redirect("student_dashboard" if request.user.role == "student" else "tutor_dashboard")

    try:
        amount = Decimal(request.POST.get("amount", "0"))
        demo_top_up(request.user, amount)
        messages.success(request, f"Баланс пополнен на {amount:.0f} ₽ в демо-режиме.")
    except (InvalidOperation, ValueError) as error:
        messages.error(request, str(error))

    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("student_dashboard" if request.user.role == "student" else "tutor_dashboard")


@login_required
def pay_listing_fee(request):
    if request.method != "POST":
        return redirect("tutor_dashboard")

    if request.user.role != "tutor":
        messages.error(request, "Размещение анкеты доступно только репетиторам.")
        return redirect("home")

    try:
        buy_platform_service(request.user, TUTOR_LISTING_FEE, Transaction.Type.LISTING_FEE)
        messages.success(request, "Размещение анкеты оплачено на 30 дней.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect("tutor_dashboard")


@login_required
def buy_pro_subscription(request):
    if request.method != "POST":
        return redirect("tutor_dashboard")

    if request.user.role != "tutor":
        messages.error(request, "Подписка Znanium Pro доступна только репетиторам.")
        return redirect("home")

    try:
        buy_platform_service(request.user, ZNANIUM_PRO_FEE, Transaction.Type.PRO_SUBSCRIPTION)
        messages.success(request, "Подписка Znanium Pro активирована на 30 дней.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect("tutor_dashboard")
