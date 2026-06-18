from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Avg
from .models import Review
from .content_filter import contains_profanity
from lessons.models import LessonOrder
from tutors.models import TutorProfile


MAX_REVIEW_TEXT_LENGTH = 2000
MAX_REVIEW_REPLY_LENGTH = 2000


@login_required
def leave_review(request, order_id):
    """Оставить отзыв после урока"""
    order = get_object_or_404(
        LessonOrder,
        id=order_id,
        student=request.user,
        status='completed'
    )
    
    # Проверяем, не оставлен ли уже отзыв
    if hasattr(order, 'review'):
        messages.info(request, 'Вы уже оставили отзыв на этот урок')
        return redirect('student_dashboard')
    
    if request.method == 'POST':
        try:
            score = int(request.POST.get('score', 5))
        except (TypeError, ValueError, OverflowError):
            messages.error(request, 'Укажите корректную оценку от 1 до 5.')
            return redirect('leave_review', order_id=order.id)
        if score < 1 or score > 5:
            messages.error(request, 'Оценка должна быть от 1 до 5.')
            return redirect('leave_review', order_id=order.id)

        text = request.POST.get('text', '').strip()[:MAX_REVIEW_TEXT_LENGTH]
        if contains_profanity(text):
            messages.error(request, 'Отзыв содержит недопустимые выражения. Пожалуйста, измените текст.')
            return redirect('leave_review', order_id=order.id)
        
        # Создаём отзыв
        Review.objects.create(
            order=order,
            student=request.user,
            tutor=order.tutor,
            score=score,
            text=text
        )
        
        # Обновляем рейтинг репетитора
        tutor_profile = order.tutor.tutor_profile
        reviews = Review.objects.filter(tutor=order.tutor)
        tutor_profile.rating = reviews.aggregate(Avg('score'))['score__avg'] or 0
        tutor_profile.review_count = reviews.count()
        tutor_profile.save()
        
        messages.success(request, 'Спасибо за отзыв!')
        return redirect('student_dashboard')
    
    context = {
        'order': order,
    }
    return render(request, 'reviews/leave_review.html', context)


@login_required
def reply_review(request, review_id):
    """Ответ репетитора на отзыв"""
    review = get_object_or_404(Review, id=review_id, tutor=request.user)
    
    if review.tutor_reply:
        messages.info(request, 'Вы уже ответили на этот отзыв')
        return redirect('tutor_dashboard')
    
    if request.method == 'POST':
        reply = request.POST.get('reply', '').strip()[:MAX_REVIEW_REPLY_LENGTH]
        if reply:
            if contains_profanity(reply):
                messages.error(request, 'Ответ содержит недопустимые выражения. Пожалуйста, измените текст.')
                return redirect('reply_review', review_id=review.id)
            review.tutor_reply = reply
            review.save()
            messages.success(request, 'Ответ опубликован')
        return redirect('tutor_dashboard')
    
    context = {
        'review': review,
    }
    return render(request, 'reviews/reply_review.html', context)
