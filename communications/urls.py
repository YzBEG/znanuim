from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_list, name='chat_list'),
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/read/', views.notifications_mark_read, name='notifications_mark_read'),
    path('<int:conversation_id>/', views.chat_detail, name='chat_detail'),
    path('start/<int:user_id>/', views.start_chat, name='start_chat'),
    path('lead/submit/', views.submit_lead, name='submit_lead'),
]
