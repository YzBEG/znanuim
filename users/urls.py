from django.urls import path
from . import views, admin_views

urlpatterns = [
    path('register/', views.register_choice, name='register_choice'),
    path('register/student/', views.register_student, name='register_student'),
    path('register/tutor/', views.register_tutor, name='register_tutor'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('personal-data-consent/', views.personal_data_consent, name='personal_data_consent'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('profile/edit/', views.tutor_profile_edit, name='tutor_profile_edit'),
    
    # Проверка пользователя
    path('check/', views.check_user, name='check_user'),
    
    # Админ-панель
    path('admin/panel/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('admin/disputes/', admin_views.disputes_list, name='disputes_list'),
    path('admin/disputes/<int:dispute_id>/', admin_views.dispute_detail, name='dispute_detail'),
    path('admin/disputes/<int:dispute_id>/resolve/', admin_views.resolve_dispute, name='resolve_dispute'),
    path('admin/moderation/', admin_views.moderation_dashboard, name='moderation_dashboard'),
    path('admin/tutor/<int:tutor_id>/', admin_views.tutor_detail_admin, name='tutor_detail_admin'),
    path('admin/tutor/<int:tutor_id>/approve/', admin_views.approve_tutor, name='approve_tutor'),
    path('admin/tutor/<int:tutor_id>/reject/', admin_views.reject_tutor, name='reject_tutor'),
    
    # Заявки с сайта
    path('admin/leads/', admin_views.lead_requests, name='lead_requests'),
    path('admin/leads/<int:lead_id>/', admin_views.lead_detail, name='lead_detail'),
    path('admin/leads/<int:lead_id>/update/', admin_views.update_lead_status, name='update_lead_status'),
]
