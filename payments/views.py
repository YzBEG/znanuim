from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import Transaction, WithdrawalRequest
from .services import (
    TUTOR_LISTING_FEE,
    ZNANIUM_PRO_FEE,
    buy_platform_service,
    create_withdrawal_request,
    get_platform_owner_user,
    get_wallet,
    service_is_active,
    service_paid_until,
    top_up_wallet,
)


def _dashboard_redirect(user):
    if user.is_staff or user.role in ["admin", "moderator"]:
        return "admin_dashboard"
    if user.role == "tutor":
        return "tutor_dashboard"
    return "student_dashboard"


@login_required
def top_up_balance(request):
    wallet = get_wallet(request.user)
    recent_transactions = Transaction.objects.filter(user=request.user).order_by("-created_at")[:20]
    payment_methods = [
        ("sbp", "СБП", "Мгновенное пополнение через систему быстрых платежей."),
        ("card", "Банковская карта", "Оплата картой с зачислением на внутренний баланс."),
        ("bank", "Банковский перевод", "Перевод на расчётный счёт платформы."),
    ]

    if request.method == "POST":
        try:
            custom_amount = (request.POST.get("custom_amount") or "").strip()
            amount = Decimal(custom_amount or request.POST.get("amount", "0"))
            method = request.POST.get("payment_method", "sbp")
            method_label = dict((value, label) for value, label, _ in payment_methods).get(method, "оплата")
            top_up_wallet(request.user, amount)
            messages.success(request, f"Баланс пополнен на {amount:.0f} ₽. Способ: {method_label}.")
        except (InvalidOperation, ValueError) as error:
            messages.error(request, str(error))

        next_url = request.POST.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(_dashboard_redirect(request.user))

    return render(
        request,
        "payments/top_up.html",
        {
            "wallet": wallet,
            "recent_transactions": recent_transactions,
            "payment_methods": payment_methods,
        },
    )


@login_required
def withdraw_funds(request):
    is_owner_withdrawal = request.user.is_staff or request.user.role == "admin"
    can_withdraw_own = request.user.role == "tutor"

    if not is_owner_withdrawal and not can_withdraw_own:
        messages.error(request, "Вывод средств доступен репетиторам и администратору платформы.")
        return redirect(_dashboard_redirect(request.user))

    target_user = get_platform_owner_user() if is_owner_withdrawal else request.user
    wallet = get_wallet(target_user)
    recent_withdrawals = WithdrawalRequest.objects.filter(tutor=target_user).order_by("-created_at")[:8]

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            requisites = request.POST.get("requisites", "")
            create_withdrawal_request(target_user, amount, requisites)
            messages.success(
                request,
                f"Заявка на вывод {amount:.0f} ₽ создана. Она ожидает обработки администратором.",
            )
            if is_owner_withdrawal:
                return redirect("admin_dashboard")
            return redirect(_dashboard_redirect(request.user))
        except (InvalidOperation, ValueError) as error:
            messages.error(request, str(error))

    return render(
        request,
        "payments/withdraw.html",
        {
            "wallet": wallet,
            "recent_withdrawals": recent_withdrawals,
            "target_user": target_user,
            "is_owner_withdrawal": is_owner_withdrawal,
        },
    )


@login_required
def pay_listing_fee(request):
    if request.method != "POST":
        return redirect("tutor_dashboard")

    if request.user.role != "tutor":
        messages.error(request, "Размещение анкеты доступно только репетиторам.")
        return redirect("home")

    try:
        buy_platform_service(request.user, TUTOR_LISTING_FEE, Transaction.Type.LISTING_FEE)
        paid_until = service_paid_until(request.user, Transaction.Type.LISTING_FEE)
        if paid_until:
            messages.success(request, f"Размещение анкеты оплачено до {paid_until:%d.%m.%Y}.")
        else:
            messages.success(request, "Размещение анкеты оплачено на 30 дней.")
    except ValueError as error:
        messages.error(request, str(error))

    return redirect("tutor_dashboard")


@login_required
def buy_pro_subscription(request):
    if request.user.role != "tutor":
        messages.error(request, "Подписка Znanium Pro доступна только репетиторам.")
        return redirect("home")

    wallet = get_wallet(request.user)
    pro_active = service_is_active(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    pro_paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)

    if request.method == "POST":
        try:
            buy_platform_service(request.user, ZNANIUM_PRO_FEE, Transaction.Type.PRO_SUBSCRIPTION)
            paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)
            if paid_until:
                messages.success(request, f"Подписка Znanium Pro продлена до {paid_until:%d.%m.%Y}.")
            else:
                messages.success(request, "Подписка Znanium Pro активирована на 30 дней.")
        except ValueError as error:
            messages.error(request, str(error))
        return redirect("buy_pro_subscription")

    return render(
        request,
        "payments/pro_subscription.html",
        {
            "wallet": wallet,
            "pro_active": pro_active,
            "pro_paid_until": pro_paid_until,
            "pro_fee": ZNANIUM_PRO_FEE,
        },
    )
