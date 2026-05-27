from django.urls import path
from . import views

urlpatterns = [
    path('slots/', views.manage_slots, name='manage_slots'),
    path('slots/<int:slot_id>/delete/', views.delete_slot, name='delete_slot'),
    path('book/<int:tutor_id>/', views.book_lesson, name='book_lesson'),
    path('orders/<int:order_id>/confirm/', views.confirm_order, name='confirm_order'),
    path('orders/<int:order_id>/reject/', views.reject_order, name='reject_order'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('orders/<int:order_id>/complete/', views.complete_lesson, name='complete_lesson'),
    path('orders/<int:order_id>/call/', views.video_lesson, name='video_lesson'),
    path('orders/<int:order_id>/materials/', views.lesson_materials, name='lesson_materials'),
    path('orders/<int:order_id>/upload/', views.upload_material, name='upload_material'),
    path('my-students/', views.my_students, name='my_students'),
]
