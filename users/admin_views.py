"""Views для админ-панели модерации"""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from communications.models import Conversation, LeadRequest, Notification, create_notification
from lessons.models import Dispute, LessonOrder
from payments.models import Transaction, WithdrawalRequest
from payments.services import complete_paid_lesson, get_platform_owner_user, get_wallet
from reviews.models import Review
from tutors.models import TutorProfile
from users.models import User


@staff_member_required
def admin_dashboard(request):
    """Главная панель администратора"""
    tutor_status_counts = dict(
        TutorProfile.objects.values_list("verification_status").annotate(count=Count("id"))
    )
    order_status_counts = dict(
        LessonOrder.objects.values_list("status").annotate(count=Count("id"))
    )
    lead_status_counts = dict(
        LeadRequest.objects.values_list("status").annotate(count=Count("id"))
    )
    platform_owner = get_platform_owner_user()
    platform_owner_wallet = get_wallet(platform_owner)
    platform_income = Transaction.objects.filter(user=platform_owner).aggregate(total=Sum("amount"))["total"] or 0
    recent_platform_transactions = Transaction.objects.filter(user=platform_owner).order_by("-created_at")[:5]
    disputes_pending = Dispute.objects.filter(decision=Dispute.Decision.PENDING).count()

    context = {
        "users_total": User.objects.count(),
        "students_total": User.objects.filter(role=User.Roles.STUDENT).count(),
        "tutors_total": User.objects.filter(role=User.Roles.TUTOR).count(),
        "staff_total": User.objects.filter(is_staff=True).count(),
        "tutors_pending": tutor_status_counts.get(TutorProfile.VerificationStatus.PENDING, 0),
        "tutors_approved": tutor_status_counts.get(TutorProfile.VerificationStatus.APPROVED, 0),
        "tutors_rejected": tutor_status_counts.get(TutorProfile.VerificationStatus.REJECTED, 0),
        "orders_total": LessonOrder.objects.count(),
        "orders_pending": order_status_counts.get(LessonOrder.Status.PENDING, 0),
        "orders_confirmed": order_status_counts.get(LessonOrder.Status.CONFIRMED, 0),
        "orders_completed": order_status_counts.get(LessonOrder.Status.COMPLETED, 0),
        "orders_in_dispute": order_status_counts.get(LessonOrder.Status.IN_DISPUTE, 0),
        "disputes_pending": disputes_pending,
        "leads_total": LeadRequest.objects.count(),
        "leads_new": lead_status_counts.get("new", 0),
        "leads_in_progress": lead_status_counts.get("in_progress", 0),
        "leads_closed": lead_status_counts.get("closed", 0),
        "conversations_total": Conversation.objects.count(),
        "reviews_total": Review.objects.count(),
        "withdrawals_pending": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(),
        "platform_owner": platform_owner,
        "platform_owner_wallet": platform_owner_wallet,
        "platform_income": platform_income,
        "recent_platform_transactions": recent_platform_transactions,
        "recent_tutors": TutorProfile.objects.select_related("user").prefetch_related("subjects").order_by("-id")[:5],
        "recent_leads": LeadRequest.objects.order_by("-created_at")[:5],
        "recent_orders": LessonOrder.objects.select_related("student", "tutor", "slot").order_by("-created_at")[:5],
        "recent_disputes": Dispute.objects.select_related("order", "order__student", "order__tutor", "order__slot", "initiated_by").order_by("-created_at")[:5],
    }
    return render(request, "custom_admin/admin_dashboard.html", context)


@staff_member_required
def disputes_list(request):
    """Список спорных уроков для администратора."""
    status_filter = request.GET.get("status") or ""
    disputes = Dispute.objects.select_related(
        "order",
        "order__student",
        "order__tutor",
        "order__slot",
        "initiated_by",
    ).order_by("-created_at")

    if status_filter:
        disputes = disputes.filter(decision=status_filter)

    context = {
        "disputes": disputes,
        "status_filter": status_filter,
        "total_count": Dispute.objects.count(),
        "pending_count": Dispute.objects.filter(decision=Dispute.Decision.PENDING).count(),
        "pay_tutor_count": Dispute.objects.filter(decision=Dispute.Decision.PAY_TUTOR).count(),
        "refund_count": Dispute.objects.filter(decision=Dispute.Decision.REFUND_STUDENT).count(),
    }
    return render(request, "custom_admin/disputes.html", context)


@staff_member_required
def dispute_detail(request, dispute_id):
    """Детальная карточка спора."""
    dispute = get_object_or_404(
        Dispute.objects.select_related(
            "order",
            "order__student",
            "order__tutor",
            "order__slot",
            "initiated_by",
        ),
        id=dispute_id,
    )
    return render(request, "custom_admin/dispute_detail.html", {"dispute": dispute})


@staff_member_required
def resolve_dispute(request, dispute_id):
    """Решение спора: оплатить репетитору или отменить без списания."""
    dispute = get_object_or_404(
        Dispute.objects.select_related("order", "order__student", "order__tutor", "order__slot"),
        id=dispute_id,
    )
    order = dispute.order

    if request.method != "POST":
        return redirect("dispute_detail", dispute_id=dispute.id)

    if dispute.decision != Dispute.Decision.PENDING or order.status != LessonOrder.Status.IN_DISPUTE:
        messages.info(request, "Этот спор уже обработан.")
        return redirect("dispute_detail", dispute_id=dispute.id)

    decision = request.POST.get("decision")
    lesson_time = timezone.localtime(order.slot.start_at).strftime("%d.%m.%Y %H:%M")

    if decision == "pay_tutor":
        try:
            complete_paid_lesson(order)
        except ValueError as error:
            messages.error(request, f"Не удалось списать оплату: {error}")
            return redirect("dispute_detail", dispute_id=dispute.id)

        order.status = LessonOrder.Status.COMPLETED
        order.save(update_fields=["status", "updated_at"])
        dispute.decision = Dispute.Decision.PAY_TUTOR
        dispute.resolved_at = timezone.now()
        dispute.save(update_fields=["decision", "resolved_at"])

        create_notification(
            recipient=order.student,
            title="Спор по уроку закрыт",
            body=f"Администратор подтвердил проведение урока на {lesson_time}. Оплата списана согласно правилам платформы.",
            url=reverse("student_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        create_notification(
            recipient=order.tutor,
            title="Спор по уроку закрыт",
            body=f"Администратор подтвердил проведение урока на {lesson_time}. Выплата начислена с учётом комиссии платформы.",
            url=reverse("tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        messages.success(request, "Спор закрыт: урок оплачен репетитору.")
        return redirect("disputes_list")

    if decision == "refund_student":
        order.status = LessonOrder.Status.CANCELLED
        order.cancelled_by = request.user
        order.cancelled_at = timezone.now()
        if order.slot_id:
            order.slot.is_booked = False
            order.slot.save(update_fields=["is_booked"])
        order.save(update_fields=["status", "cancelled_by", "cancelled_at", "updated_at"])
        dispute.decision = Dispute.Decision.REFUND_STUDENT
        dispute.resolved_at = timezone.now()
        dispute.save(update_fields=["decision", "resolved_at"])

        create_notification(
            recipient=order.student,
            title="Спор по уроку закрыт",
            body=f"Администратор отменил урок на {lesson_time}. Оплата по нему не списана.",
            url=reverse("student_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        create_notification(
            recipient=order.tutor,
            title="Спор по уроку закрыт",
            body=f"Администратор отменил урок на {lesson_time}. Выплата по нему не начислена.",
            url=reverse("tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        messages.success(request, "Спор закрыт: урок отменён без оплаты.")
        return redirect("disputes_list")

    messages.error(request, "Выберите корректное решение по спору.")
    return redirect("dispute_detail", dispute_id=dispute.id)


@staff_member_required
def moderation_dashboard(request):
    """Панель модерации репетиторов"""
    pending = TutorProfile.objects.filter(
        verification_status=TutorProfile.VerificationStatus.PENDING
    ).select_related('user').prefetch_related('subjects').order_by('id')
    
    approved = TutorProfile.objects.filter(
        verification_status=TutorProfile.VerificationStatus.APPROVED
    ).select_related('user').count()
    
    rejected = TutorProfile.objects.filter(
        verification_status=TutorProfile.VerificationStatus.REJECTED
    ).select_related('user').count()
    
    context = {
        'pending_tutors': pending,
        'approved_count': approved,
        'rejected_count': rejected,
    }
    return render(request, 'custom_admin/moderation_dashboard.html', context)


@staff_member_required
def approve_tutor(request, tutor_id):
    """Одобрить репетитора"""
    tutor = get_object_or_404(TutorProfile, id=tutor_id)
    if tutor.verification_status != TutorProfile.VerificationStatus.PENDING:
        messages.info(request, "Анкета уже обработана.")
        return redirect("tutor_detail_admin", tutor_id=tutor.id)
    tutor.verification_status = TutorProfile.VerificationStatus.APPROVED
    tutor.save()
    messages.success(request, f'Репетитор {tutor.user.get_full_name()} одобрен')
    return redirect('moderation_dashboard')


@staff_member_required
def reject_tutor(request, tutor_id):
    """Отклонить репетитора"""
    tutor = get_object_or_404(TutorProfile, id=tutor_id)

    if tutor.verification_status != TutorProfile.VerificationStatus.PENDING:
        messages.info(request, "Анкета уже обработана.")
        return redirect("tutor_detail_admin", tutor_id=tutor.id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        tutor.verification_status = TutorProfile.VerificationStatus.REJECTED
        tutor.save()
        # TODO: отправить уведомление репетитору с причиной отклонения
        messages.warning(request, f'Репетитор {tutor.user.get_full_name()} отклонён')
        return redirect('moderation_dashboard')
    
    return render(request, 'custom_admin/reject_tutor.html', {'tutor': tutor})


@staff_member_required
def tutor_detail_admin(request, tutor_id):
    """Детальный просмотр анкеты репетитора для модерации"""
    tutor = get_object_or_404(
        TutorProfile.objects.select_related('user').prefetch_related('subjects'),
        id=tutor_id
    )
    return render(request, 'custom_admin/tutor_detail_admin.html', {'tutor': tutor})



@staff_member_required
def lead_requests(request):
    """Список всех заявок с сайта"""
    from communications.models import LeadRequest
    from django.db.models import Q
    
    leads = LeadRequest.objects.all()
    
    # Фильтрация по статусу
    status_filter = request.GET.get('status')
    if status_filter:
        leads = leads.filter(status=status_filter)
    
    # Поиск
    search = request.GET.get('search')
    if search:
        leads = leads.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(subject__icontains=search)
        )
    
    # Статистика
    total_count = LeadRequest.objects.count()
    new_count = LeadRequest.objects.filter(status='new').count()
    in_progress_count = LeadRequest.objects.filter(status='in_progress').count()
    closed_count = LeadRequest.objects.filter(status='closed').count()
    
    context = {
        'leads': leads,
        'total_count': total_count,
        'new_count': new_count,
        'in_progress_count': in_progress_count,
        'closed_count': closed_count,
    }
    return render(request, 'custom_admin/lead_requests.html', context)


@staff_member_required
def lead_detail(request, lead_id):
    """Детальный просмотр заявки"""
    from communications.models import LeadRequest
    
    lead = get_object_or_404(LeadRequest, id=lead_id)
    return render(request, 'custom_admin/lead_detail.html', {'lead': lead})


@staff_member_required
def update_lead_status(request, lead_id):
    """Обновление статуса заявки"""
    from communications.models import LeadRequest
    
    lead = get_object_or_404(LeadRequest, id=lead_id)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        lead.status = status
        lead.notes = notes
        lead.save()
        
        messages.success(request, 'Статус заявки обновлён')
        return redirect('lead_detail', lead_id=lead_id)
    
    return redirect('lead_detail', lead_id=lead_id)
