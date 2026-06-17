import os
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from communications.models import Notification, create_notification
from payments.services import complete_paid_lesson, get_wallet, money, tutor_publication_is_active
from tutors.models import TutorProfile

from .models import AvailabilitySlot, Dispute, LessonMaterial, LessonOrder, LessonSession


def _lesson_time_text(order):
    return f"{timezone.localtime(order.slot.start_at):%d.%m.%Y %H:%M}"


def _is_telemost_link(url):
    normalized = url.lower()
    return normalized.startswith("https://") and (
        "telemost.yandex." in normalized or "yandex.ru/telemost" in normalized
    )


ALLOWED_MATERIAL_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "jpg",
    "jpeg",
    "png",
    "zip",
}
MAX_MATERIAL_FILE_SIZE = 20 * 1024 * 1024


@login_required
def manage_slots(request):
    if request.user.role != "tutor":
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    try:
        profile = request.user.tutor_profile
    except TutorProfile.DoesNotExist:
        messages.error(request, "Сначала заполните профиль репетитора.")
        return redirect("tutor_profile_edit")

    if request.method == "POST":
        date = request.POST.get("date")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")

        try:
            start_dt = timezone.make_aware(datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M"))
            end_dt = timezone.make_aware(datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M"))

            if start_dt.date() <= timezone.localdate():
                messages.error(request, "Расписание можно добавлять минимум на следующий день.")
            elif end_dt <= start_dt:
                messages.error(request, "Время окончания должно быть позже времени начала.")
            elif start_dt < timezone.now():
                messages.error(request, "Нельзя создать слот в прошлом.")
            elif AvailabilitySlot.objects.filter(
                tutor=profile,
                start_at__lt=end_dt,
                end_at__gt=start_dt,
            ).exists():
                messages.error(
                    request,
                    "Это время уже занято или пересекается с другим слотом. Выберите другой интервал.",
                )
            else:
                try:
                    AvailabilitySlot.objects.create(
                        tutor=profile,
                        start_at=start_dt,
                        end_at=end_dt,
                    )
                    messages.success(request, "Слот добавлен.")
                    return redirect("manage_slots")
                except IntegrityError:
                    messages.error(request, "Такой слот уже существует. Выберите другое время.")
        except ValueError:
            messages.error(request, "Неверный формат даты или времени.")

    today = timezone.localdate()
    first_available_date = today + timedelta(days=1)
    weekday_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    month_names = [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    date_options = []
    for day_offset in range(30):
        option_date = first_available_date + timedelta(days=day_offset)
        label = f"{option_date.day} {month_names[option_date.month - 1]}, {weekday_names[option_date.weekday()]}"
        if day_offset == 0:
            label += " · завтра"
        date_options.append(
            {
                "value": option_date.strftime("%Y-%m-%d"),
                "label": label,
            }
        )

    time_options = []
    for hour in range(8, 23):
        for minute in (0, 30):
            time_options.append(f"{hour:02d}:{minute:02d}")

    existing_slots = list(
        AvailabilitySlot.objects.filter(
            tutor=profile,
            start_at__date__gte=first_available_date,
            start_at__date__lte=first_available_date + timedelta(days=29),
        ).values("start_at", "end_at")
    )
    available_time_options_by_date = {}
    for option in date_options:
        available_times = []
        for time_value in time_options:
            slot_dt = timezone.make_aware(datetime.strptime(f"{option['value']} {time_value}", "%Y-%m-%d %H:%M"))
            default_end_dt = slot_dt + timedelta(hours=1)
            overlaps_existing = any(
                existing["start_at"] < default_end_dt and existing["end_at"] > slot_dt
                for existing in existing_slots
            )
            if not overlaps_existing:
                available_times.append(time_value)
        available_time_options_by_date[option["value"]] = available_times

    slots = AvailabilitySlot.objects.filter(
        tutor=profile,
        start_at__gte=timezone.now(),
        start_at__lte=timezone.now() + timedelta(days=30),
    ).order_by("start_at")

    return render(
        request,
        "lessons/manage_slots.html",
        {
            "slots": slots,
            "today": today,
            "date_options": date_options,
            "time_options": time_options,
            "available_time_options_by_date": available_time_options_by_date,
        },
    )


@login_required
def delete_slot(request, slot_id):
    slot = get_object_or_404(AvailabilitySlot, id=slot_id, tutor__user=request.user)

    active_orders = LessonOrder.objects.filter(
        slot=slot,
        status__in=[LessonOrder.Status.PENDING, LessonOrder.Status.CONFIRMED],
    )

    if active_orders.exists():
        messages.error(request, "Нельзя удалить слот с активными заявками.")
    else:
        LessonOrder.objects.filter(slot=slot, status=LessonOrder.Status.CANCELLED).delete()
        try:
            slot.delete()
            messages.success(request, "Слот удалён.")
        except Exception as error:
            messages.error(request, f"Ошибка при удалении слота: {error}")

    return redirect("manage_slots")


@login_required
def book_lesson(request, tutor_id):
    if request.user.role != "student":
        messages.error(request, "Только ученики могут бронировать уроки.")
        return redirect("tutor_catalog")

    tutor_profile = get_object_or_404(TutorProfile, id=tutor_id, verification_status=TutorProfile.VerificationStatus.APPROVED)
    if not tutor_publication_is_active(tutor_profile.user):
        messages.error(request, "Анкета преподавателя пока не опубликована. Выберите другого репетитора в каталоге.")
        return redirect("tutor_catalog")

    if request.method == "POST":
        slot_id = request.POST.get("slot_id")
        try:
            slot_id = int(slot_id)
        except (TypeError, ValueError):
            messages.error(request, "Выберите корректный свободный слот.")
            return redirect("book_lesson", tutor_id=tutor_profile.id)

        wallet = get_wallet(request.user)
        lesson_price = money(tutor_profile.price_per_hour)

        if wallet.balance < lesson_price:
            messages.error(
                request,
                f"Для записи нужно {lesson_price:.0f} ₽. Пополните баланс в личном кабинете.",
            )
            return redirect("student_dashboard")

        try:
            with transaction.atomic():
                slot = AvailabilitySlot.objects.select_for_update().get(
                    id=slot_id,
                    tutor=tutor_profile,
                    is_booked=False,
                )
                order = LessonOrder.objects.create(
                    student=request.user,
                    tutor=tutor_profile.user,
                    slot=slot,
                    price=tutor_profile.price_per_hour,
                    status=LessonOrder.Status.PENDING,
                )
                slot.is_booked = True
                slot.save(update_fields=["is_booked"])
        except AvailabilitySlot.DoesNotExist:
            messages.error(request, "Этот слот уже занят или недоступен. Выберите другое время.")
            return redirect("book_lesson", tutor_id=tutor_profile.id)
        except IntegrityError:
            messages.error(request, "Этот слот уже занят. Выберите другое время.")
            return redirect("book_lesson", tutor_id=tutor_profile.id)

        create_notification(
            recipient=tutor_profile.user,
            title="Новая заявка на урок",
            body=f"{request.user.get_full_name() or request.user.username} хочет записаться на {_lesson_time_text(order)}.",
            url=reverse("tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )

        messages.success(request, "Заявка отправлена. Ожидайте подтверждения от репетитора.")
        return redirect("student_dashboard")

    available_slots = AvailabilitySlot.objects.filter(
        tutor=tutor_profile,
        is_booked=False,
        start_at__gte=timezone.now(),
    ).order_by("start_at")[:20]
    student_wallet = get_wallet(request.user)
    lesson_price = money(tutor_profile.price_per_hour)

    return render(
        request,
        "lessons/book_lesson.html",
        {
            "tutor": tutor_profile,
            "slots": available_slots,
            "wallet": student_wallet,
            "lesson_price": lesson_price,
            "has_enough_balance": student_wallet.balance >= lesson_price,
        },
    )


@login_required
def confirm_order(request, order_id):
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status=LessonOrder.Status.PENDING)
    order.status = LessonOrder.Status.CONFIRMED
    order.save(update_fields=["status", "updated_at"])
    LessonSession.objects.get_or_create(order=order, defaults={"room_name": f"lesson-{order.id}"})
    create_notification(
        recipient=order.student,
        title="Урок подтверждён",
        body=f"{request.user.get_full_name() or request.user.username} подтвердил занятие на {_lesson_time_text(order)}.",
        url=reverse("video_lesson", args=[order.id]),
        kind=Notification.Kind.LESSON,
    )
    messages.success(request, "Заявка подтверждена.")
    return redirect("tutor_dashboard")


@login_required
def reject_order(request, order_id):
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status=LessonOrder.Status.PENDING)
    student = order.student
    lesson_time = _lesson_time_text(order)

    order.slot.is_booked = False
    order.slot.save(update_fields=["is_booked"])
    order.delete()

    create_notification(
        recipient=student,
        title="Заявка отклонена",
        body=f"Репетитор не смог принять занятие на {lesson_time}. Выберите другой слот.",
        url=reverse("tutor_catalog"),
        kind=Notification.Kind.LESSON,
    )

    messages.info(request, "Заявка отклонена.")
    return redirect("tutor_dashboard")


@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(
        LessonOrder.objects.select_related("student", "tutor", "slot"),
        id=order_id,
    )
    if request.user not in (order.student, order.tutor):
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    lesson_time = _lesson_time_text(order)
    other_user = order.tutor if request.user == order.student else order.student
    redirect_to = "student_dashboard" if request.user == order.student else "tutor_dashboard"

    if order.status == LessonOrder.Status.PENDING and request.user == order.student:
        order.slot.is_booked = False
        order.slot.save(update_fields=["is_booked"])
        order.delete()
        create_notification(
            recipient=other_user,
            title="Заявка отменена",
            body=f"{request.user.get_full_name() or request.user.username} отменил заявку на {lesson_time}.",
            url=reverse("tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        messages.info(request, "Заявка отменена.")
        return redirect(redirect_to)

    if order.status == LessonOrder.Status.CONFIRMED:
        order.status = LessonOrder.Status.CANCELLED
        order.cancelled_by = request.user
        order.cancelled_at = timezone.now()
        order.slot.is_booked = False
        order.slot.save(update_fields=["is_booked"])
        order.save(update_fields=["status", "cancelled_by", "cancelled_at", "updated_at"])
        create_notification(
            recipient=other_user,
            title="Урок отменён",
            body=f"{request.user.get_full_name() or request.user.username} отменил занятие на {lesson_time}.",
            url=reverse("student_dashboard" if other_user == order.student else "tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        messages.info(request, "Урок отменён. Оплата по нему не списывается.")
        return redirect(redirect_to)

    messages.error(request, "Этот урок уже нельзя отменить обычным способом.")
    return redirect(redirect_to)


@login_required
def complete_lesson(request, order_id):
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status=LessonOrder.Status.CONFIRMED)
    order.status = LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION
    order.tutor_completed_at = timezone.now()
    order.save(update_fields=["status", "tutor_completed_at", "updated_at"])
    if hasattr(order, "session"):
        order.session.ended_at = timezone.now()
        order.session.save(update_fields=["ended_at"])
    create_notification(
        recipient=order.student,
        title="Подтвердите проведение урока",
        body=f"{request.user.get_full_name() or request.user.username} отметил занятие как проведённое. Подтвердите урок или сообщите о проблеме.",
        url=reverse("student_dashboard"),
        kind=Notification.Kind.LESSON,
    )
    messages.success(request, "Урок отправлен ученику на подтверждение. Деньги будут начислены после подтверждения.")
    return redirect("tutor_dashboard")


@login_required
def confirm_lesson_completion(request, order_id):
    order = get_object_or_404(
        LessonOrder,
        id=order_id,
        student=request.user,
        status=LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
    )
    try:
        payment_created = complete_paid_lesson(order)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("student_dashboard")

    order.status = LessonOrder.Status.COMPLETED
    order.student_confirmed_at = timezone.now()
    order.save(update_fields=["status", "student_confirmed_at", "updated_at"])
    create_notification(
        recipient=order.tutor,
        title="Урок подтверждён",
        body=f"{request.user.get_full_name() or request.user.username} подтвердил проведение занятия на {_lesson_time_text(order)}.",
        url=reverse("tutor_dashboard"),
        kind=Notification.Kind.LESSON,
    )
    if payment_created:
        messages.success(request, "Урок подтверждён. Оплата списана, репетитору начислена выплата с учётом комиссии платформы.")
    else:
        messages.success(request, "Урок уже был подтверждён и оплачен ранее.")
    return redirect("student_dashboard")


@login_required
def dispute_lesson_completion(request, order_id):
    order = get_object_or_404(
        LessonOrder,
        id=order_id,
        student=request.user,
        status=LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
    )
    reason = request.POST.get("reason", "").strip() if request.method == "POST" else ""
    if not reason:
        reason = "Ученик сообщил о проблеме после завершения урока."

    order.status = LessonOrder.Status.IN_DISPUTE
    order.save(update_fields=["status", "updated_at"])
    Dispute.objects.update_or_create(
        order=order,
        defaults={
            "initiated_by": request.user,
            "reason": reason,
        },
    )
    create_notification(
        recipient=order.tutor,
        title="Урок переведён в спор",
        body=f"{request.user.get_full_name() or request.user.username} не подтвердил занятие на {_lesson_time_text(order)}.",
        url=reverse("tutor_dashboard"),
        kind=Notification.Kind.LESSON,
    )
    messages.warning(request, "Урок переведён в спор. Оплата не будет начислена репетитору до решения администратора.")
    return redirect("student_dashboard")


@login_required
def upload_material(request, order_id):
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "")
        file = request.FILES.get("file")

        if not file or not title:
            messages.error(request, "Заполните название и выберите файл.")
        elif file.size > MAX_MATERIAL_FILE_SIZE:
            messages.error(request, "Файл слишком большой. Максимальный размер материала — 20 МБ.")
        elif file.name.split(".")[-1].lower() not in ALLOWED_MATERIAL_EXTENSIONS:
            messages.error(request, "Недопустимый тип файла. Загрузите документ, презентацию, таблицу, изображение или zip-архив.")
        else:
            LessonMaterial.objects.create(
                order=order,
                title=title,
                description=description,
                file=file,
                uploaded_by=request.user,
            )
            create_notification(
                recipient=order.student,
                title="Добавлен материал к уроку",
                body=f"{title} доступен в материалах занятия.",
                url=reverse("lesson_materials", args=[order.id]),
                kind=Notification.Kind.LESSON,
            )
            messages.success(request, "Материал загружен.")

        return redirect("lesson_materials", order_id=order_id)

    return render(request, "lessons/upload_material.html", {"order": order})


@login_required
def download_material(request, material_id):
    material = get_object_or_404(
        LessonMaterial.objects.select_related("order", "order__student", "order__tutor"),
        id=material_id,
    )
    order = material.order

    if request.user not in [order.student, order.tutor]:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    if not material.file or not material.file.storage.exists(material.file.name):
        messages.error(request, "Файл недоступен. Загрузите материал повторно.")
        return redirect("lesson_materials", order_id=order.id)

    filename = os.path.basename(material.file.name)
    return FileResponse(material.file.open("rb"), as_attachment=True, filename=filename)


@login_required
def lesson_materials(request, order_id):
    order = get_object_or_404(LessonOrder, id=order_id)

    if request.user not in [order.student, order.tutor]:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    materials = LessonMaterial.objects.filter(order=order)

    return render(
        request,
        "lessons/materials.html",
        {
            "order": order,
            "materials": materials,
            "is_tutor": request.user == order.tutor,
        },
    )


@login_required
def video_lesson(request, order_id):
    order = get_object_or_404(
        LessonOrder.objects.select_related("student", "tutor", "slot"),
        id=order_id,
    )

    if request.user not in [order.student, order.tutor]:
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    if order.status not in [
        LessonOrder.Status.CONFIRMED,
        LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
    ]:
        messages.error(request, "Страница урока доступна только для подтверждённых занятий.")
        if request.user == order.tutor:
            return redirect("tutor_dashboard")
        return redirect("student_dashboard")

    if request.user == order.student and order.status == LessonOrder.Status.CONFIRMED:
        wallet = get_wallet(request.user)
        if wallet.balance < money(order.price):
            messages.error(request, "Недостаточно средств для начала урока. Пополните баланс.")
            return redirect("student_dashboard")

    session, _ = LessonSession.objects.get_or_create(
        order=order,
        defaults={"room_name": f"lesson-{order.id}"},
    )

    if request.method == "POST":
        if request.user != order.tutor:
            messages.error(request, "Отправлять ссылку на урок может только репетитор.")
            return redirect("video_lesson", order_id=order.id)

        meeting_url = (request.POST.get("meeting_url") or "").strip()
        validator = URLValidator(schemes=["https"])
        try:
            validator(meeting_url)
        except ValidationError:
            messages.error(request, "Вставьте корректную HTTPS-ссылку на встречу в Яндекс Телемост.")
            return redirect("video_lesson", order_id=order.id)

        if not _is_telemost_link(meeting_url):
            messages.error(request, "Ссылка должна вести на встречу Яндекс Телемост.")
            return redirect("video_lesson", order_id=order.id)

        session.meeting_url = meeting_url
        session.save(update_fields=["meeting_url"])
        create_notification(
            recipient=order.student,
            title="Ссылка на видеоурок",
            body=f"{request.user.get_full_name() or request.user.username} отправил ссылку на занятие {_lesson_time_text(order)}.",
            url=reverse("video_lesson", args=[order.id]),
            kind=Notification.Kind.LESSON,
        )
        messages.success(request, "Ссылка на видеоурок отправлена ученику.")
        return redirect("video_lesson", order_id=order.id)

    return render(
        request,
        "lessons/video_room.html",
        {
            "order": order,
            "session": session,
            "is_tutor": request.user == order.tutor,
            "telemost_create_url": settings.EXTERNAL_MEETING_BASE_URL.rstrip("/"),
            "lesson_meeting_url": session.meeting_url,
        },
    )


@login_required
def my_students(request):
    if request.user.role != "tutor":
        messages.error(request, "Доступ запрещён.")
        return redirect("home")

    orders = LessonOrder.objects.filter(
        tutor=request.user,
        status__in=[
            LessonOrder.Status.CONFIRMED,
            LessonOrder.Status.AWAITING_STUDENT_CONFIRMATION,
            LessonOrder.Status.COMPLETED,
            LessonOrder.Status.CANCELLED,
            LessonOrder.Status.IN_DISPUTE,
        ],
    ).select_related("student", "slot").order_by("-slot__start_at")

    students_dict = {}
    for order in orders:
        student_id = order.student.id
        if student_id not in students_dict:
            students_dict[student_id] = {
                "student": order.student,
                "lessons": [],
            }
        students_dict[student_id]["lessons"].append(order)

    return render(request, "lessons/my_students.html", {"students_data": list(students_dict.values())})
