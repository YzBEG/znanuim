from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("design/home-redesign/", views.design_home_redesign, name="design_home_redesign"),
    path("catalog/", views.tutor_catalog, name="tutor_catalog"),
    path("tutors/<int:tutor_id>/", views.tutor_detail, name="tutor_detail"),
    path("tutors/<int:tutor_id>/reviews/", views.tutor_reviews, name="tutor_reviews"),
]
