import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Проверяем аутентификацию
        if not self.scope["user"].is_authenticated:
            await self.close()
            return
        
        # Проверяем доступ к чату
        has_access = await self.check_access()
        if not has_access:
            await self.close()
            return
        
        # Присоединяемся к группе чата
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Покидаем группу чата
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'chat_message':
            text = data.get('text', '').strip()
            
            if not text:
                return
            
            # Сохраняем сообщение в БД
            message = await self.save_message(text)
            
            if message:
                # Отправляем сообщение всем в группе
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': {
                            'id': message['id'],
                            'text': message['text'],
                            'sender_id': message['sender_id'],
                            'sender_name': message['sender_name'],
                            'created_at': message['created_at'],
                        }
                    }
                )
    
    async def chat_message(self, event):
        # Отправляем сообщение в WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))
    
    @database_sync_to_async
    def check_access(self):
        """Проверяем, имеет ли пользователь доступ к чату"""
        from .models import Conversation
        
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            user = self.scope["user"]
            return user in [conversation.student, conversation.tutor]
        except Conversation.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, text):
        """Сохраняем сообщение в БД"""
        from .models import Conversation, Message, Notification, create_notification
        
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            user = self.scope["user"]
            
            # Создаём сообщение
            message = Message.objects.create(
                conversation=conversation,
                sender=user,
                text=text
            )
            
            # Проверяем на запрещённый контент
            if message.has_forbidden_content():
                message.delete()
                return None

            recipient = conversation.tutor if user == conversation.student else conversation.student
            create_notification(
                recipient=recipient,
                title="Новое сообщение",
                body=f"{user.get_full_name() or user.username}: {message.text[:80]}",
                url=f"/chat/{conversation.id}/",
                kind=Notification.Kind.MESSAGE,
            )
            
            return {
                'id': message.id,
                'text': message.text,
                'sender_id': message.sender.id,
                'sender_name': message.sender.get_full_name(),
                'created_at': message.created_at.isoformat(),
            }
        except Exception as e:
            print(f"Error saving message: {e}")
            return None


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        self.group_name = f"notifications_{self.scope['user'].id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "notifications_state",
            **await self.get_state(),
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get("type") == "mark_read":
            await self.mark_read(data.get("id"))
            await self.send(text_data=json.dumps({
                "type": "notifications_state",
                **await self.get_state(),
            }))

    async def notification_created(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification_created",
            "notification": event["notification"],
            "unread_count": event["unread_count"],
        }))

    @database_sync_to_async
    def get_state(self):
        from .models import Notification

        user = self.scope["user"]
        latest = Notification.objects.filter(recipient=user, is_read=False)[:8]
        return {
            "unread_count": Notification.objects.filter(recipient=user, is_read=False).count(),
            "notifications": [notification.as_dict() for notification in latest],
        }

    @database_sync_to_async
    def mark_read(self, notification_id=None):
        from .models import Notification

        queryset = Notification.objects.filter(recipient=self.scope["user"], is_read=False)
        if notification_id:
            queryset = queryset.filter(id=notification_id)
        queryset.update(is_read=True)


class VideoCallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.room_group_name = f"video_lesson_{self.order_id}"

        has_access = await self.check_access()
        if not has_access:
            await self.close()
            return

        await self.mark_joined()
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "video_signal",
                "signal_type": "participant_joined",
                "sender_id": self.scope["user"].id,
                "sender_name": self.scope["user"].get_full_name() or self.scope["user"].username,
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "video_signal",
                    "signal_type": "participant_left",
                    "sender_id": self.scope["user"].id,
                    "sender_name": self.scope["user"].get_full_name() or self.scope["user"].username,
                },
            )
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        allowed_types = {
            "ready",
            "offer",
            "answer",
            "ice-candidate",
            "camera-state",
            "mic-state",
            "call-ended",
        }
        signal_type = data.get("type")
        if signal_type not in allowed_types:
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "video_signal",
                "signal_type": signal_type,
                "sender_id": self.scope["user"].id,
                "sender_name": self.scope["user"].get_full_name() or self.scope["user"].username,
                "payload": data,
            },
        )

    async def video_signal(self, event):
        await self.send(text_data=json.dumps({
            "type": event["signal_type"],
            "sender_id": event["sender_id"],
            "sender_name": event.get("sender_name", ""),
            **event.get("payload", {}),
        }))

    @database_sync_to_async
    def check_access(self):
        from lessons.models import LessonOrder

        try:
            order = LessonOrder.objects.select_related("student", "tutor").get(id=self.order_id)
        except LessonOrder.DoesNotExist:
            return False

        user = self.scope["user"]
        return (
            order.status == LessonOrder.Status.CONFIRMED
            and user in [order.student, order.tutor]
        )

    @database_sync_to_async
    def mark_joined(self):
        from lessons.models import LessonOrder, LessonSession

        order = LessonOrder.objects.select_related("student", "tutor").get(id=self.order_id)
        session, _ = LessonSession.objects.get_or_create(
            order=order,
            defaults={"room_name": f"lesson-{order.id}"},
        )
        now = timezone.now()
        if session.started_at is None:
            session.started_at = now
        if self.scope["user"] == order.tutor:
            session.tutor_joined_at = now
        else:
            session.student_joined_at = now
        session.save(update_fields=["started_at", "tutor_joined_at", "student_joined_at"])
