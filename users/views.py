from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import StudentRegistrationForm, TutorRegistrationForm
from .models import User


def register_choice(request):
    return render(request, "users/register_choice.html")


def register_student(request):
    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Добро пожаловать! Аккаунт ученика создан.")
            return redirect("student_dashboard")
    else:
        form = StudentRegistrationForm()
    return render(request, "users/register_student.html", {"form": form})


def register_tutor(request):
    if request.method == "POST":
        form = TutorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Добро пожаловать! Теперь заполните анкету репетитора.")
            return redirect("tutor_profile_edit")
    else:
        form = TutorRegistrationForm()
    return render(request, "users/register_tutor.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Добро пожаловать, {user.get_full_name() or user.username}!")

            if user.is_staff or user.role in [User.Roles.ADMIN, User.Roles.MODERATOR]:
                return redirect("admin_dashboard")
            if user.role == User.Roles.STUDENT:
                return redirect("student_dashboard")
            if user.role == User.Roles.TUTOR:
                return redirect("tutor_dashboard")
            return redirect("home")

        messages.error(request, "Неверный логин или пароль.")

    return render(request, "users/login.html")


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "Вы вышли из системы.")
    return redirect("home")


@login_required
def student_dashboard(request):
    if request.user.role != User.Roles.STUDENT:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    from lessons.models import LessonOrder
    from payments.models import Transaction, Wallet

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(user=request.user).order_by("-created_at")[:6]

    upcoming_lessons = LessonOrder.objects.filter(
        student=request.user,
        status__in=[
            LessonOrder.Status.CONFIRMED,
            LessonOrder.Status.PENDING,
            LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
        ],
    ).select_related("tutor", "slot").order_by("slot__start_at")[:5]

    past_lessons = LessonOrder.objects.filter(
        student=request.user,
        status=LessonOrder.Status.COMPLETED,
    ).select_related("tutor", "slot").order_by("-slot__start_at")[:10]

    grouped_orders = LessonOrder.objects.filter(
        student=request.user,
        status__in=[
            LessonOrder.Status.PENDING,
            LessonOrder.Status.CONFIRMED,
            LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
            LessonOrder.Status.COMPLETED,
            LessonOrder.Status.CANCELLED,
            LessonOrder.Status.IN_DISPUTE,
        ],
    ).select_related(
        "tutor",
        "slot",
        "tutor__tutor_profile",
        "review",
    ).prefetch_related("materials").order_by(
        "tutor__last_name",
        "tutor__first_name",
        "-slot__start_at",
    )[:60]

    lesson_groups_map = OrderedDict()
    for order in grouped_orders:
        tutor = order.tutor
        profile = getattr(tutor, "tutor_profile", None)
        order.has_review = hasattr(order, "review")
        group = lesson_groups_map.setdefault(
            tutor.id,
            {
                "tutor": tutor,
                "profile": profile,
                "photo_url": profile.avatar_url if profile and profile.avatar_url else "",
                "orders": [],
                "upcoming_count": 0,
                "past_count": 0,
                "materials_count": 0,
            },
        )
        group["orders"].append(order)
        group["materials_count"] += len(getattr(order, "_prefetched_objects_cache", {}).get("materials", []))
        if order.status in [LessonOrder.Status.COMPLETED, LessonOrder.Status.CANCELLED, LessonOrder.Status.IN_DISPUTE]:
            group["past_count"] += 1
        else:
            group["upcoming_count"] += 1
    lesson_groups = list(lesson_groups_map.values())
    student_materials_count = sum(group["materials_count"] for group in lesson_groups)

    return render(
        request,
        "users/student_dashboard.html",
        {
            "wallet": wallet,
            "recent_transactions": recent_transactions,
            "upcoming_lessons": upcoming_lessons,
            "past_lessons": past_lessons,
            "lesson_groups": lesson_groups,
            "student_materials_count": student_materials_count,
        },
    )


@login_required
def tutor_dashboard(request):
    if request.user.role != User.Roles.TUTOR:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    from lessons.models import LessonOrder
    from payments.models import Transaction, Wallet
    from payments.services import (
        TUTOR_LISTING_FEE,
        ZNANIUM_PRO_FEE,
        service_is_active,
        service_paid_until,
    )
    from reviews.models import Review
    from tutors.models import ProfileView, TutorProfile

    try:
        profile = request.user.tutor_profile
    except TutorProfile.DoesNotExist:
        messages.warning(request, "Пожалуйста, заполните профиль репетитора.")
        return redirect("tutor_profile_edit")

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(user=request.user).order_by("-created_at")[:6]
    listing_active = service_is_active(request.user, Transaction.Type.LISTING_FEE)
    listing_paid_until = service_paid_until(request.user, Transaction.Type.LISTING_FEE)
    pro_active = service_is_active(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    pro_paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)

    pending_orders = LessonOrder.objects.filter(
        tutor=request.user,
        status=LessonOrder.Status.PENDING,
    ).select_related("student", "slot").order_by("created_at")[:10]

    upcoming_lessons = LessonOrder.objects.filter(
        tutor=request.user,
        status__in=[
            LessonOrder.Status.CONFIRMED,
            LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
        ],
    ).select_related("student", "slot").order_by("slot__start_at")[:10]

    total_lessons = LessonOrder.objects.filter(
        tutor=request.user,
        status=LessonOrder.Status.COMPLETED,
    ).count()

    total_views = ProfileView.objects.filter(tutor=profile).count()
    views_last_7_days = ProfileView.objects.filter(
        tutor=profile,
        viewed_at__gte=timezone.now() - timedelta(days=7),
    ).count()
    views_last_30_days = ProfileView.objects.filter(
        tutor=profile,
        viewed_at__gte=timezone.now() - timedelta(days=30),
    ).count()

    reviews_without_reply = Review.objects.filter(
        tutor=request.user,
        tutor_reply__isnull=True,
    ).select_related("student", "order").order_by("-created_at")[:5]

    all_reviews = Review.objects.filter(tutor=request.user).select_related("student", "order").order_by("-created_at")[:10]

    return render(
        request,
        "users/tutor_dashboard.html",
        {
            "profile": profile,
            "wallet": wallet,
            "recent_transactions": recent_transactions,
            "listing_active": listing_active,
            "listing_paid_until": listing_paid_until,
            "pro_active": pro_active,
            "pro_paid_until": pro_paid_until,
            "listing_fee": TUTOR_LISTING_FEE,
            "pro_fee": ZNANIUM_PRO_FEE,
            "pending_orders": pending_orders,
            "upcoming_lessons": upcoming_lessons,
            "total_lessons": total_lessons,
            "total_views": total_views,
            "views_last_7_days": views_last_7_days,
            "views_last_30_days": views_last_30_days,
            "reviews_without_reply": reviews_without_reply,
            "all_reviews": all_reviews,
        },
    )


@login_required
def tutor_profile_edit(request):
    if request.user.role != User.Roles.TUTOR:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    from payments.models import Transaction
    from payments.services import service_is_active, service_paid_until
    from tutors.models import Subject, TutorProfile

    profile, _ = TutorProfile.objects.get_or_create(
        user=request.user,
        defaults={"price_per_hour": 1000, "lesson_format": TutorProfile.LessonFormat.ONLINE},
    )
    pro_active = service_is_active(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    pro_paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)

    if request.method == "POST":
        request.user.first_name = request.POST.get("first_name", request.user.first_name)
        request.user.last_name = request.POST.get("last_name", request.user.last_name)
        request.user.email = request.POST.get("email", request.user.email)
        request.user.phone = request.POST.get("phone", request.user.phone)
        request.user.save(update_fields=["first_name", "last_name", "email", "phone"])

        profile.bio = request.POST.get("bio", "")
        profile.experience_years = int(request.POST.get("experience_years", 0))
        profile.price_per_hour = float(request.POST.get("price_per_hour", 1000))
        profile.lesson_format = TutorProfile.LessonFormat.ONLINE
        profile.city = ""

        if "diploma" in request.FILES:
            profile.diploma = request.FILES["diploma"]
        if "photo_file" in request.FILES:
            profile.photo_file = request.FILES["photo_file"]
        if "intro_video" in request.FILES:
            if pro_active:
                profile.intro_video = request.FILES["intro_video"]
            else:
                messages.warning(
                    request,
                    "Загрузка видео-анкеты доступна репетиторам с подпиской Znanium Pro.",
                )

        profile.save()
        subject_ids = request.POST.getlist("subjects")
        profile.subjects.set(Subject.objects.filter(id__in=subject_ids))

        messages.success(request, "Профиль обновлён. Если анкета ещё не проходила модерацию, дождитесь проверки.")
        return redirect("tutor_dashboard")

    subjects = Subject.objects.filter(parent__isnull=True)

    return render(
        request,
        "users/tutor_profile_edit.html",
        {
            "profile": profile,
            "subjects": subjects,
            "pro_active": pro_active,
            "pro_paid_until": pro_paid_until,
        },
    )


def check_user(request):
    return render(request, "check_user.html")


def privacy_policy(request):
    return render(request, "users/privacy_policy.html")


def personal_data_consent(request):
    return render(request, "users/personal_data_consent.html")


def page_not_found(request, exception=None, unmatched_path=None):
    return render(request, "404.html", status=404)
