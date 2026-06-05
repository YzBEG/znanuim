from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from .forms import StudentRegistrationForm, TutorRegistrationForm
from .models import User


def register_choice(request):
    """Выбор роли при регистрации"""
    return render(request, 'users/register_choice.html')


def register_student(request):
    """Регистрация ученика"""
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Добро пожаловать! Ваш аккаунт ученика создан.')
            return redirect('student_dashboard')
    else:
        form = StudentRegistrationForm()
    return render(request, 'users/register_student.html', {'form': form})


def register_tutor(request):
    """Регистрация репетитора"""
    if request.method == 'POST':
        form = TutorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Добро пожаловать! Теперь заполните анкету репетитора.')
            return redirect('tutor_profile_edit')
    else:
        form = TutorRegistrationForm()
    return render(request, 'users/register_tutor.html', {'form': form})


def login_view(request):
    """Вход в систему"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.get_full_name() or user.username}!')
            
            # Редирект в зависимости от роли
            if user.is_staff or user.role in [User.Roles.ADMIN, User.Roles.MODERATOR]:
                return redirect('admin_dashboard')
            elif user.role == User.Roles.STUDENT:
                return redirect('student_dashboard')
            elif user.role == User.Roles.TUTOR:
                return redirect('tutor_dashboard')
            else:
                return redirect('home')
        else:
            messages.error(request, 'Неверный логин или пароль')
    
    return render(request, 'users/login.html')


@login_required
def logout_view(request):
    """Выход из системы"""
    logout(request)
    messages.info(request, 'Вы вышли из системы')
    return redirect('home')


@login_required
def student_dashboard(request):
    """Личный кабинет ученика"""
    if request.user.role != User.Roles.STUDENT:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    from collections import OrderedDict
    from lessons.models import LessonOrder
    from payments.models import Transaction, Wallet
    
    # Получаем или создаём кошелёк
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:6]
    
    # Предстоящие уроки
    upcoming_lessons = LessonOrder.objects.filter(
        student=request.user,
        status__in=[LessonOrder.Status.CONFIRMED, LessonOrder.Status.PENDING]
    ).select_related('tutor', 'slot').order_by('slot__start_at')[:5]
    
    # История уроков
    past_lessons = LessonOrder.objects.filter(
        student=request.user,
        status=LessonOrder.Status.COMPLETED
    ).select_related('tutor', 'slot').order_by('-slot__start_at')[:10]

    grouped_orders = LessonOrder.objects.filter(
        student=request.user,
        status__in=[
            LessonOrder.Status.PENDING,
            LessonOrder.Status.CONFIRMED,
            LessonOrder.Status.COMPLETED,
        ],
    ).select_related(
        'tutor',
        'slot',
        'tutor__tutor_profile',
        'review',
    ).prefetch_related('materials').order_by(
        'tutor__last_name',
        'tutor__first_name',
        '-slot__start_at',
    )[:60]

    lesson_groups_map = OrderedDict()
    for order in grouped_orders:
        tutor = order.tutor
        profile = getattr(tutor, 'tutor_profile', None)
        order.has_review = hasattr(order, 'review')
        group = lesson_groups_map.setdefault(tutor.id, {
            'tutor': tutor,
            'profile': profile,
            'photo_url': profile.avatar_url if profile and profile.avatar_url else '',
            'orders': [],
            'upcoming_count': 0,
            'past_count': 0,
            'materials_count': 0,
        })
        group['orders'].append(order)
        group['materials_count'] += len(getattr(order, '_prefetched_objects_cache', {}).get('materials', []))
        if order.status == LessonOrder.Status.COMPLETED:
            group['past_count'] += 1
        else:
            group['upcoming_count'] += 1
    lesson_groups = list(lesson_groups_map.values())
    student_materials_count = sum(group['materials_count'] for group in lesson_groups)

    context = {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
        'upcoming_lessons': upcoming_lessons,
        'past_lessons': past_lessons,
        'lesson_groups': lesson_groups,
        'student_materials_count': student_materials_count,
    }
    return render(request, 'users/student_dashboard.html', context)


@login_required
def tutor_dashboard(request):
    """Личный кабинет репетитора"""
    if request.user.role != User.Roles.TUTOR:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    from lessons.models import LessonOrder, AvailabilitySlot
    from payments.models import Transaction, Wallet
    from payments.services import (
        TUTOR_LISTING_FEE,
        ZNANIUM_PRO_FEE,
        service_is_active,
        service_paid_until,
    )
    from tutors.models import TutorProfile
    
    # Проверяем наличие профиля
    try:
        profile = request.user.tutor_profile
    except TutorProfile.DoesNotExist:
        messages.warning(request, 'Пожалуйста, заполните профиль репетитора')
        return redirect('tutor_profile_edit')
    
    # Получаем или создаём кошелёк
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:6]
    listing_active = service_is_active(request.user, Transaction.Type.LISTING_FEE)
    listing_paid_until = service_paid_until(request.user, Transaction.Type.LISTING_FEE)
    pro_active = service_is_active(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    pro_paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    
    # Заявки от учеников (ожидают подтверждения)
    pending_orders = LessonOrder.objects.filter(
        tutor=request.user,
        status=LessonOrder.Status.PENDING
    ).select_related('student', 'slot').order_by('created_at')[:10]
    
    # Предстоящие уроки
    upcoming_lessons = LessonOrder.objects.filter(
        tutor=request.user,
        status=LessonOrder.Status.CONFIRMED
    ).select_related('student', 'slot').order_by('slot__start_at')[:10]
    
    # Статистика
    total_lessons = LessonOrder.objects.filter(
        tutor=request.user,
        status=LessonOrder.Status.COMPLETED
    ).count()
    
    # Статистика просмотров
    from tutors.models import ProfileView
    from datetime import timedelta
    
    total_views = ProfileView.objects.filter(tutor=profile).count()
    views_last_7_days = ProfileView.objects.filter(
        tutor=profile,
        viewed_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    views_last_30_days = ProfileView.objects.filter(
        tutor=profile,
        viewed_at__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    # Отзывы без ответа
    from reviews.models import Review
    reviews_without_reply = Review.objects.filter(
        tutor=request.user,
        tutor_reply__isnull=True
    ).select_related('student', 'order').order_by('-created_at')[:5]
    
    # Все отзывы
    all_reviews = Review.objects.filter(
        tutor=request.user
    ).select_related('student', 'order').order_by('-created_at')[:10]
    
    context = {
        'profile': profile,
        'wallet': wallet,
        'recent_transactions': recent_transactions,
        'listing_active': listing_active,
        'listing_paid_until': listing_paid_until,
        'pro_active': pro_active,
        'pro_paid_until': pro_paid_until,
        'listing_fee': TUTOR_LISTING_FEE,
        'pro_fee': ZNANIUM_PRO_FEE,
        'pending_orders': pending_orders,
        'upcoming_lessons': upcoming_lessons,
        'total_lessons': total_lessons,
        'total_views': total_views,
        'views_last_7_days': views_last_7_days,
        'views_last_30_days': views_last_30_days,
        'reviews_without_reply': reviews_without_reply,
        'all_reviews': all_reviews,
    }
    return render(request, 'users/tutor_dashboard.html', context)


@login_required
def tutor_profile_edit(request):
    """Редактирование анкеты репетитора"""
    if request.user.role != User.Roles.TUTOR:
        messages.error(request, 'Доступ запрещён')
        return redirect('home')
    
    from payments.models import Transaction
    from payments.services import service_is_active, service_paid_until
    from tutors.models import TutorProfile, Subject
    
    # Получаем или создаём профиль
    profile, created = TutorProfile.objects.get_or_create(
        user=request.user,
        defaults={'price_per_hour': 1000}
    )
    pro_active = service_is_active(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    pro_paid_until = service_paid_until(request.user, Transaction.Type.PRO_SUBSCRIPTION)
    
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        request.user.phone = request.POST.get('phone', request.user.phone)
        request.user.save(update_fields=['first_name', 'last_name', 'email', 'phone'])

        profile.bio = request.POST.get('bio', '')
        profile.experience_years = int(request.POST.get('experience_years', 0))
        profile.price_per_hour = float(request.POST.get('price_per_hour', 1000))
        profile.lesson_format = request.POST.get('lesson_format', 'online')
        profile.city = request.POST.get('city', '')
        
        # Обработка файлов - только если загружены новые
        if 'diploma' in request.FILES:
            profile.diploma = request.FILES['diploma']
        if 'photo_file' in request.FILES:
            profile.photo_file = request.FILES['photo_file']
        if 'intro_video' in request.FILES:
            if pro_active:
                profile.intro_video = request.FILES['intro_video']
            else:
                messages.warning(
                    request,
                    'Загрузка видео-анкеты доступна репетиторам с подпиской Znanium Pro.',
                )
        
        # Сохраняем профиль
        profile.save()
        
        # Обработка предметов (после save, чтобы M2M работал)
        subject_ids = request.POST.getlist('subjects')
        profile.subjects.set(Subject.objects.filter(id__in=subject_ids))
        
        messages.success(request, 'Профиль обновлён! Ожидайте модерации.')
        return redirect('tutor_dashboard')
    
    subjects = Subject.objects.filter(parent__isnull=True)
    
    context = {
        'profile': profile,
        'subjects': subjects,
        'pro_active': pro_active,
        'pro_paid_until': pro_paid_until,
    }
    return render(request, 'users/tutor_profile_edit.html', context)


def check_user(request):
    """Страница проверки текущего пользователя"""
    return render(request, 'check_user.html')


def page_not_found(request, exception=None, unmatched_path=None):
    return render(request, '404.html', status=404)
