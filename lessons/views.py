import os
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from .models import AvailabilitySlot, LessonOrder, LessonSession
from communications.models import Notification, create_notification
from payments.services import complete_paid_lesson, get_wallet, money
from tutors.models import TutorProfile


def _lesson_time_text(order):
    return f"{timezone.localtime(order.slot.start_at):%d.%m.%Y %H:%M}"


@login_required
def manage_slots(request):
    """Управление слотами репетитора"""
    if request.user.role != 'tutor':
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    try:
        profile = request.user.tutor_profile
    except TutorProfile.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль репетитора')
        return redirect('tutor_profile_edit')
    
    if request.method == 'POST':
        date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        
        try:
            start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
            
            # Делаем timezone-aware
            start_dt = timezone.make_aware(start_dt)
            end_dt = timezone.make_aware(end_dt)
            
            if start_dt.date() <= timezone.localdate():
                messages.error(request, 'Расписание можно добавлять минимум на следующий день.')
            elif end_dt <= start_dt:
                messages.error(request, 'Время окончания должно быть позже времени начала')
            elif start_dt < timezone.now():
                messages.error(request, 'Нельзя создать слот в прошлом')
            elif AvailabilitySlot.objects.filter(
                tutor=profile,
                start_at__lt=end_dt,
                end_at__gt=start_dt,
            ).exists():
                messages.error(request, 'Это время уже занято или пересекается с другим слотом. Выберите другой интервал.')
            else:
                try:
                    AvailabilitySlot.objects.create(
                        tutor=profile,
                        start_at=start_dt,
                        end_at=end_dt
                    )
                    messages.success(request, 'Слот добавлен')
                    return redirect('manage_slots')
                except IntegrityError:
                    messages.error(request, 'Такой слот уже существует. Выберите другое время.')
        except ValueError:
            messages.error(request, 'Неверный формат даты или времени')
    
    today = timezone.localdate()
    first_available_date = today + timedelta(days=1)
    weekday_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    month_names = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    date_options = []
    for day_offset in range(30):
        option_date = first_available_date + timedelta(days=day_offset)
        label = f"{option_date.day} {month_names[option_date.month - 1]}, {weekday_names[option_date.weekday()]}"
        if day_offset == 0:
            label += " · завтра"
        date_options.append({
            "value": option_date.strftime("%Y-%m-%d"),
            "label": label,
        })

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
            slot_dt = datetime.strptime(f"{option['value']} {time_value}", "%Y-%m-%d %H:%M")
            slot_dt = timezone.make_aware(slot_dt)
            default_end_dt = slot_dt + timedelta(hours=1)
            overlaps_existing = any(
                existing["start_at"] < default_end_dt and existing["end_at"] > slot_dt
                for existing in existing_slots
            )
            if not overlaps_existing:
                available_times.append(time_value)
        available_time_options_by_date[option["value"]] = available_times

    # Получаем слоты на ближайшие 30 дней
    slots = AvailabilitySlot.objects.filter(
        tutor=profile,
        start_at__gte=timezone.now(),
        start_at__lte=timezone.now() + timedelta(days=30)
    ).order_by('start_at')
    
    context = {
        'slots': slots,
        'today': today,
        'date_options': date_options,
        'time_options': time_options,
        'available_time_options_by_date': available_time_options_by_date,
    }
    return render(request, 'lessons/manage_slots.html', context)


@login_required
def delete_slot(request, slot_id):
    """Удаление слота"""
    slot = get_object_or_404(AvailabilitySlot, id=slot_id, tutor__user=request.user)
    
    # Проверяем, есть ли активные заказы (не отменённые)
    active_orders = LessonOrder.objects.filter(
        slot=slot,
        status__in=[LessonOrder.Status.PENDING, LessonOrder.Status.CONFIRMED]
    )
    
    if active_orders.exists():
        messages.error(request, 'Нельзя удалить слот с активными заказами')
    else:
        # Удаляем все отменённые заказы для этого слота
        LessonOrder.objects.filter(slot=slot, status=LessonOrder.Status.CANCELLED).delete()
        
        # Теперь можем удалить слот
        try:
            slot.delete()
            messages.success(request, 'Слот удалён')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении слота: {str(e)}')
    
    return redirect('manage_slots')


@login_required
def book_lesson(request, tutor_id):
    """Бронирование урока учеником"""
    if request.user.role != 'student':
        messages.error(request, 'Только ученики могут бронировать уроки')
        return redirect('tutor_catalog')
    
    tutor_profile = get_object_or_404(TutorProfile, id=tutor_id, verification_status='approved')
    
    if request.method == 'POST':
        slot_id = request.POST.get('slot_id')
        slot = get_object_or_404(AvailabilitySlot, id=slot_id, tutor=tutor_profile, is_booked=False)
        wallet = get_wallet(request.user)
        lesson_price = money(tutor_profile.price_per_hour)

        if wallet.balance < lesson_price:
            messages.error(
                request,
                f"Для записи нужно {lesson_price:.0f} ₽. Пополните демо-баланс в личном кабинете.",
            )
            return redirect('student_dashboard')
        
        # Создаём заказ
        order = LessonOrder.objects.create(
            student=request.user,
            tutor=tutor_profile.user,
            slot=slot,
            price=tutor_profile.price_per_hour,
            status='pending'
        )
        
        # Помечаем слот как забронированный
        slot.is_booked = True
        slot.save()

        create_notification(
            recipient=tutor_profile.user,
            title="Новая заявка на урок",
            body=f"{request.user.get_full_name() or request.user.username} хочет записаться на {_lesson_time_text(order)}.",
            url=reverse("tutor_dashboard"),
            kind=Notification.Kind.LESSON,
        )
        
        messages.success(request, 'Заявка отправлена! Ожидайте подтверждения от репетитора.')
        return redirect('student_dashboard')
    
    # Получаем доступные слоты
    available_slots = AvailabilitySlot.objects.filter(
        tutor=tutor_profile,
        is_booked=False,
        start_at__gte=timezone.now()
    ).order_by('start_at')[:20]
    student_wallet = get_wallet(request.user)
    lesson_price = money(tutor_profile.price_per_hour)
    
    context = {
        'tutor': tutor_profile,
        'slots': available_slots,
        'wallet': student_wallet,
        'lesson_price': lesson_price,
        'has_enough_balance': student_wallet.balance >= lesson_price,
    }
    return render(request, 'lessons/book_lesson.html', context)


@login_required
def confirm_order(request, order_id):
    """Подтверждение заказа репетитором"""
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status='pending')
    order.status = 'confirmed'
    order.save()
    LessonSession.objects.get_or_create(order=order, defaults={"room_name": f"lesson-{order.id}"})
    create_notification(
        recipient=order.student,
        title="Урок подтверждён",
        body=f"{request.user.get_full_name() or request.user.username} подтвердил занятие на {_lesson_time_text(order)}.",
        url=reverse("video_lesson", args=[order.id]),
        kind=Notification.Kind.LESSON,
    )
    messages.success(request, 'Заявка подтверждена')
    return redirect('tutor_dashboard')


@login_required
def reject_order(request, order_id):
    """Отклонение заказа репетитором"""
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status='pending')
    student = order.student
    lesson_time = _lesson_time_text(order)
    
    # Освобождаем слот
    order.slot.is_booked = False
    order.slot.save()
    
    # УДАЛЯЕМ заказ вместо изменения статуса
    # Это освобождает слот для повторного бронирования
    order.delete()

    create_notification(
        recipient=student,
        title="Заявка отклонена",
        body=f"Репетитор не смог принять занятие на {lesson_time}. Выберите другой слот.",
        url=reverse("tutor_catalog"),
        kind=Notification.Kind.LESSON,
    )
    
    messages.info(request, 'Заявка отклонена')
    return redirect('tutor_dashboard')


@login_required
def cancel_order(request, order_id):
    """Отмена заказа студентом"""
    order = get_object_or_404(LessonOrder, id=order_id, student=request.user, status='pending')
    tutor = order.tutor
    lesson_time = _lesson_time_text(order)
    
    # Освобождаем слот
    order.slot.is_booked = False
    order.slot.save()
    
    # Удаляем заказ
    order.delete()

    create_notification(
        recipient=tutor,
        title="Заявка отменена",
        body=f"{request.user.get_full_name() or request.user.username} отменил заявку на {lesson_time}.",
        url=reverse("tutor_dashboard"),
        kind=Notification.Kind.LESSON,
    )
    
    messages.info(request, 'Заявка отменена')
    return redirect('student_dashboard')



@login_required
def complete_lesson(request, order_id):
    """Завершение урока репетитором"""
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user, status='confirmed')
    try:
        payment_created = complete_paid_lesson(order)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('tutor_dashboard')

    order.status = 'completed'
    order.save()
    if hasattr(order, "session"):
        order.session.ended_at = timezone.now()
        order.session.save(update_fields=["ended_at"])
    create_notification(
        recipient=order.student,
        title="Урок завершён",
        body=f"Занятие с {request.user.get_full_name() or request.user.username} отмечено как проведённое.",
        url=reverse("lesson_materials", args=[order.id]),
        kind=Notification.Kind.LESSON,
    )
    if payment_created:
        messages.success(request, 'Урок завершён. Оплата списана, выплата и комиссия рассчитаны.')
    else:
        messages.success(request, 'Урок уже был завершён и оплачен ранее.')
    return redirect('tutor_dashboard')


@login_required
def upload_material(request, order_id):
    """Загрузка материала к уроку"""
    order = get_object_or_404(LessonOrder, id=order_id, tutor=request.user)
    
    if request.method == 'POST':
        from .models import LessonMaterial
        
        title = request.POST.get('title', '')
        description = request.POST.get('description', '')
        file = request.FILES.get('file')
        
        if file and title:
            LessonMaterial.objects.create(
                order=order,
                title=title,
                description=description,
                file=file,
                uploaded_by=request.user
            )
            create_notification(
                recipient=order.student,
                title="Добавлен материал к уроку",
                body=f"{title} доступен в материалах занятия.",
                url=reverse("lesson_materials", args=[order.id]),
                kind=Notification.Kind.LESSON,
            )
            messages.success(request, 'Материал загружен')
        else:
            messages.error(request, 'Заполните все поля')
        
        return redirect('lesson_materials', order_id=order_id)
    
    return render(request, 'lessons/upload_material.html', {'order': order})


@login_required
def download_material(request, material_id):
    """Безопасное скачивание материала участниками урока."""
    from .models import LessonMaterial

    material = get_object_or_404(
        LessonMaterial.objects.select_related("order", "order__student", "order__tutor"),
        id=material_id,
    )
    order = material.order

    if request.user not in [order.student, order.tutor]:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')

    if not material.file or not material.file.storage.exists(material.file.name):
        messages.error(request, 'Файл недоступен. Загрузите материал повторно.')
        return redirect('lesson_materials', order_id=order.id)

    filename = os.path.basename(material.file.name)
    return FileResponse(material.file.open('rb'), as_attachment=True, filename=filename)


@login_required
def lesson_materials(request, order_id):
    """Просмотр материалов к уроку"""
    order = get_object_or_404(LessonOrder, id=order_id)
    
    # Проверяем доступ
    if request.user != order.student and request.user != order.tutor:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    from .models import LessonMaterial
    materials = LessonMaterial.objects.filter(order=order)
    
    context = {
        'order': order,
        'materials': materials,
        'is_tutor': request.user == order.tutor,
    }
    return render(request, 'lessons/materials.html', context)


@login_required
def video_lesson(request, order_id):
    """Видеокомната подтверждённого урока"""
    order = get_object_or_404(
        LessonOrder.objects.select_related("student", "tutor", "slot"),
        id=order_id,
    )

    if request.user not in [order.student, order.tutor]:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')

    if order.status != LessonOrder.Status.CONFIRMED:
        messages.error(request, 'Видеоурок доступен только для подтверждённых занятий')
        if request.user == order.tutor:
            return redirect('tutor_dashboard')
        return redirect('student_dashboard')

    if request.user == order.student:
        wallet = get_wallet(request.user)
        if wallet.balance < money(order.price):
            messages.error(request, 'Недостаточно средств для начала урока. Пополните демо-баланс.')
            return redirect('student_dashboard')

    session, _ = LessonSession.objects.get_or_create(
        order=order,
        defaults={"room_name": f"lesson-{order.id}"},
    )
    meeting_url = settings.EXTERNAL_MEETING_BASE_URL.rstrip('/')

    return render(request, 'lessons/video_room.html', {
        'order': order,
        'session': session,
        'is_tutor': request.user == order.tutor,
        'meeting_url': meeting_url,
    })


@login_required
def my_students(request):
    """Список учеников репетитора с уроками"""
    if request.user.role != 'tutor':
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    # Получаем все завершённые и подтверждённые уроки
    orders = LessonOrder.objects.filter(
        tutor=request.user,
        status__in=['confirmed', 'completed']
    ).select_related('student', 'slot').order_by('-slot__start_at')
    
    # Группируем по студентам
    students_dict = {}
    for order in orders:
        student_id = order.student.id
        if student_id not in students_dict:
            students_dict[student_id] = {
                'student': order.student,
                'lessons': []
            }
        students_dict[student_id]['lessons'].append(order)
    
    context = {
        'students_data': list(students_dict.values()),
    }
    return render(request, 'lessons/my_students.html', context)
