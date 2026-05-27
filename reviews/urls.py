from django.urls import path
from . import views

urlpatterns = [
    path('leave/<int:order_id>/', views.leave_review, name='leave_review'),
    path('reply/<int:review_id>/', views.reply_review, name='reply_review'),
]
