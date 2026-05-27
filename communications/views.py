from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from .models import Conversation, Message, Notification, create_notification
from users.models import User


@login_required
def chat_list(request):
    """Список всех чатов пользователя"""
    if request.user.role == 'student':
        conversations = Conversation.objects.filter(student=request.user).select_related('tutor')
    elif request.user.role == 'tutor':
        conversations = Conversation.objects.filter(tutor=request.user).select_related('student')
    else:
        conversations = []
    
    # Добавляем последнее сообщение к каждому чату
    for conv in conversations:
        conv.last_message = conv.messages.order_by('-created_at').first()
    
    context = {
        'conversations': conversations,
    }
    return render(request, 'communications/chat_list.html', context)


@login_required
def chat_detail(request, conversation_id):
    """Детальный просмотр чата"""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id
    )
    
    # Проверяем доступ
    if request.user != conversation.student and request.user != conversation.tutor:
        messages.error(request, 'Доступ запрещён')
        return redirect('chat_list')
    
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        attachment = request.FILES.get('attachment')
        
        if text or attachment:
            message = Message(
                conversation=conversation,
                sender=request.user,
                text=text
            )
            
            if attachment:
                message.attachment = attachment
            
            # Проверяем на запрещённый контент
            if message.has_forbidden_content():
                messages.error(request, 'Сообщение содержит запрещённые ссылки. Обменивайтесь контактами только после первой оплаты.')
            else:
                message.save()
                recipient = conversation.tutor if request.user == conversation.student else conversation.student
                create_notification(
                    recipient=recipient,
                    title='Новое сообщение',
                    body=f"{request.user.get_full_name() or request.user.username}: {(message.text or 'Файл')[:80]}",
                    url=f"/chat/{conversation.id}/",
                    kind=Notification.Kind.MESSAGE,
                )
                return redirect('chat_detail', conversation_id=conversation_id)
    
    # Получаем сообщения
    chat_messages = conversation.messages.select_related('sender').order_by('created_at')
    
    # Определяем собеседника
    if request.user == conversation.student:
        other_user = conversation.tutor
    else:
        other_user = conversation.student
    
    context = {
        'conversation': conversation,
        'chat_messages': chat_messages,
        'other_user': other_user,
    }
    return render(request, 'communications/chat_detail.html', context)


@login_required
def start_chat(request, user_id):
    """Начать чат с пользователем"""
    other_user = get_object_or_404(User, id=user_id)
    
    # Определяем роли
    if request.user.role == 'student' and other_user.role == 'tutor':
        conversation, created = Conversation.objects.get_or_create(
            student=request.user,
            tutor=other_user
        )
    elif request.user.role == 'tutor' and other_user.role == 'student':
        conversation, created = Conversation.objects.get_or_create(
            student=other_user,
            tutor=request.user
        )
    else:
        messages.error(request, 'Чат возможен только между учеником и репетитором')
        return redirect('home')
    
    return redirect('chat_detail', conversation_id=conversation.id)


@login_required
@ensure_csrf_cookie
def notifications_list(request):
    notifications = Notification.objects.filter(recipient=request.user)[:8]
    return JsonResponse({
        "unread_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
        "notifications": [notification.as_dict() for notification in notifications],
    })


@login_required
@require_POST
def notifications_mark_read(request):
    notification_id = request.POST.get("id")
    queryset = Notification.objects.filter(recipient=request.user, is_read=False)
    if notification_id:
        queryset = queryset.filter(id=notification_id)
    queryset.update(is_read=True)
    return JsonResponse({
        "ok": True,
        "unread_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
    })



def submit_lead(request):
    """Обработка заявки с главной страницы"""
    if request.method == 'POST':
        from .models import LeadRequest
        
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        subject = request.POST.get('subject', '').strip()
        goal = request.POST.get('goal', 'grades')
        
        if name and phone and subject:
            LeadRequest.objects.create(
                name=name,
                phone=phone,
                subject=subject,
                goal=goal
            )
            messages.success(request, 'Заявка отправлена. Мы свяжемся с вами в ближайшее время.')
        else:
            messages.error(request, 'Пожалуйста, заполните все поля.')
    
    next_url = request.POST.get('next', '')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect('home')
