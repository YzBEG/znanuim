from django.urls import path

from . import views


urlpatterns = [
    path("top-up/", views.top_up_balance, name="top_up_balance"),
    path("listing/", views.pay_listing_fee, name="pay_listing_fee"),
    path("pro/", views.buy_pro_subscription, name="buy_pro_subscription"),
]
