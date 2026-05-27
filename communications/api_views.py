from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from .models import LeadRequest, Conversation, Message
from .serializers import LeadRequestSerializer, ConversationSerializer, MessageSerializer


class LeadRequestViewSet(viewsets.ModelViewSet):
    """API для заявок с сайта"""
    serializer_class = LeadRequestSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            # Создание заявки доступно всем
            return [AllowAny()]
        else:
            # Просмотр и редактирование только для админов
            return [IsAdminUser()]
    
    def get_queryset(self):
        queryset = LeadRequest.objects.all()
        
        # Фильтр по статусу
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Обновить статус заявки"""
        lead = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if new_status not in dict(LeadRequest.STATUS_CHOICES):
            return Response(
                {'error': 'Неверный статус'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lead.status = new_status
        lead.notes = notes
        lead.save()
        
        serializer = self.get_serializer(lead)
        return Response(serializer.data)


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """API для чатов"""
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Conversation.objects.filter(student=user).select_related('tutor')
        elif user.role == 'tutor':
            return Conversation.objects.filter(tutor=user).select_related('student')
        return Conversation.objects.none()
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Получить сообщения чата"""
        conversation = self.get_object()
        messages = conversation.messages.select_related('sender').order_by('created_at')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Отправить сообщение в чат"""
        conversation = self.get_object()
        
        # Проверяем доступ
        if request.user not in [conversation.student, conversation.tutor]:
            return Response(
                {'error': 'Доступ запрещён'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        text = request.data.get('text', '').strip()
        if not text:
            return Response(
                {'error': 'Текст сообщения обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            text=text
        )
        
        # Проверяем на запрещённый контент
        if message.has_forbidden_content():
            message.delete()
            return Response(
                {'error': 'Сообщение содержит запрещённые ссылки'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """API для сообщений"""
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        # Пользователь видит только сообщения из своих чатов
        return Message.objects.filter(
            conversation__student=user
        ) | Message.objects.filter(
            conversation__tutor=user
        )
