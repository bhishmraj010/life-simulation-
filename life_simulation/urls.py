from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/',     admin.site.urls),
    path('users/',     include('users.urls')),
    path('dashboard/', include('tasks.urls')),
    path('tracker/',   include('tracker.urls')),
    path('reports/',   include('reports.urls')),
    # Root → redirect to dashboard (or login if not authenticated)
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('diet/', include('diet.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)