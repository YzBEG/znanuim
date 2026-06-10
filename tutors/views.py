from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Subject, TutorProfile


def home(request):
    if request.method == "POST":
        messages.success(request, "Спасибо! Заявка принята. Мы свяжемся с вами в ближайшее время.")
        return redirect(reverse("home") + "#lead")

    return render(request, "design/home_redesign.html")


def design_home_redesign(request):
    return redirect("home")


def tutor_catalog(request):
    from payments.models import Transaction

    active_service_user_ids = set(Transaction.objects.filter(
        type__in=[Transaction.Type.LISTING_FEE, Transaction.Type.PRO_SUBSCRIPTION],
        amount__gt=0,
    ).values_list("user_id", flat=True))
    active_pro_user_ids = {
        user_id
        for user_id in active_service_user_ids
        if service_is_active_id(user_id, Transaction.Type.PRO_SUBSCRIPTION)
    }
    active_listing_user_ids = {
        user_id
        for user_id in active_service_user_ids
        if service_is_active_id(user_id, Transaction.Type.LISTING_FEE)
    }
    published_user_ids = active_listing_user_ids | active_pro_user_ids
    pro_lookup_user_ids = active_pro_user_ids or {-1}
    published_lookup_user_ids = published_user_ids or {-1}

    tutors = TutorProfile.objects.select_related("user").prefetch_related("subjects").filter(
        verification_status=TutorProfile.VerificationStatus.APPROVED,
        user_id__in=published_lookup_user_ids,
        lesson_format__in=[TutorProfile.LessonFormat.ONLINE, TutorProfile.LessonFormat.BOTH],
    ).annotate(
        pro_rank=Case(
            When(user_id__in=pro_lookup_user_ids, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    )

    subject_id = request.GET.get("subject")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    q = request.GET.get("q")
    sort = request.GET.get("sort") or "rating"

    if subject_id:
        tutors = tutors.filter(subjects__id=subject_id)
    if min_price:
        tutors = tutors.filter(price_per_hour__gte=min_price)
    if max_price:
        tutors = tutors.filter(price_per_hour__lte=max_price)
    if q:
        tutors = tutors.filter(
            Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(bio__icontains=q)
            | Q(subjects__name__icontains=q)
        )

    tutors = tutors.distinct()
    sort_options = {
        "rating": ("-pro_rank", "-rating", "-review_count"),
        "price_asc": ("-pro_rank", "price_per_hour", "-rating"),
        "price_desc": ("-pro_rank", "-price_per_hour", "-rating"),
        "experience": ("-pro_rank", "-experience_years", "-rating"),
    }
    tutors = tutors.order_by(*sort_options.get(sort, sort_options["rating"]))

    online_since = timezone.now() - timedelta(minutes=15)
    for tutor in tutors:
        tutor.has_pro = tutor.user_id in active_pro_user_ids
        tutor.is_online = bool(tutor.user.last_login and tutor.user.last_login >= online_since)
        tutor.publication_paid = tutor.user_id in published_user_ids

    return render(
        request,
        "tutors/catalog.html",
        {
            "tutors": tutors,
            "subjects": Subject.objects.all(),
            "filters": {
                "subject": subject_id or "",
                "min_price": min_price or "",
                "max_price": max_price or "",
                "q": q or "",
                "sort": sort,
            },
        },
    )


def service_is_active_id(user_id, transaction_type):
    from django.contrib.auth import get_user_model
    from payments.services import service_is_active

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    return bool(user and service_is_active(user, transaction_type))


def tutor_detail(request, tutor_id):
    tutor = get_object_or_404(
        TutorProfile.objects.select_related("user").prefetch_related("subjects"),
        id=tutor_id,
    )

    from payments.models import Transaction
    from payments.services import service_is_active, tutor_publication_is_active

    is_owner = request.user.is_authenticated and request.user == tutor.user
    is_staff_viewer = request.user.is_authenticated and (request.user.is_staff or request.user.role in ["admin", "moderator"])
    publication_active = tutor_publication_is_active(tutor.user)

    if tutor.verification_status != TutorProfile.VerificationStatus.APPROVED or not publication_active:
        return render(
            request,
            "tutors/profile_unavailable.html",
            {
                "tutor": tutor,
                "is_owner": is_owner,
                "is_staff_viewer": is_staff_viewer,
                "publication_active": publication_active,
            },
            status=200 if is_owner or is_staff_viewer else 404,
        )
    
    # Учёт просмотра профиля
    from .models import ProfileView
    
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    ProfileView.objects.create(
        tutor=tutor,
        viewer=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request)
    )
    
    # Получаем отзывы
    from reviews.models import Review
    reviews = Review.objects.filter(tutor=tutor.user).select_related('student').order_by('-created_at')
    last_login = tutor.user.last_login
    tutor_is_online = bool(last_login and timezone.now() - last_login <= timedelta(minutes=15))
    tutor_has_pro = service_is_active(tutor.user, Transaction.Type.PRO_SUBSCRIPTION)
    
    return render(request, "tutors/detail.html", {
        "tutor": tutor,
        "reviews": reviews,
        "tutor_is_online": tutor_is_online,
        "tutor_has_pro": tutor_has_pro,
    })



def tutor_reviews(request, tutor_id):
    """Просмотр отзывов репетитора"""
    tutor_profile = get_object_or_404(TutorProfile, id=tutor_id, verification_status='approved')
    
    from reviews.models import Review
    reviews = Review.objects.filter(tutor=tutor_profile.user).select_related('student').order_by('-created_at')
    
    context = {
        'tutor': tutor_profile,
        'reviews': reviews,
    }
    return render(request, 'tutors/reviews.html', context)
