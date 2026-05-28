from rest_framework import serializers
from .models import LeadRequest, Conversation, Message
from tutors.serializers import UserSerializer


class LeadRequestSerializer(serializers.ModelSerializer):
    goal_display = serializers.CharField(source='get_goal_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = LeadRequest
        fields = [
            'id', 'name', 'phone', 'subject', 'goal', 'goal_display',
            'status', 'status_display', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'notes', 'created_at', 'updated_at']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    sender_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_name', 'text', 'created_at']
        read_only_fields = ['id', 'sender', 'created_at']
    
    def get_sender_name(self, obj):
        return obj.sender.get_full_name()


class ConversationSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    tutor = UserSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    messages_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'student', 'tutor', 'is_paid_relationship',
            'last_message', 'messages_count', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'text': last_msg.text[:50] + '...' if len(last_msg.text) > 50 else last_msg.text,
                'created_at': last_msg.created_at
            }
        return None
    
    def get_messages_count(self, obj):
        return obj.messages.count()
