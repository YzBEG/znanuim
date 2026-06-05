"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from users.views import page_not_found

handler404 = 'users.views.page_not_found'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('config.api_urls')),  # REST API
    path('accounts/', include('users.urls')),
    path('lessons/', include('lessons.urls')),
    path('payments/', include('payments.urls')),
    path('chat/', include('communications.urls')),
    path('reviews/', include('reviews.urls')),
    path('', include('tutors.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()

urlpatterns += [
    path('<path:unmatched_path>', page_not_found, name='custom_404'),
]
