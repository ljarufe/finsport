from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('bet', include('bet.urls')),
    path('api/', include('rest_framework.urls', namespace='rest_framework')),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(
        settings.STATIC_URL, document_root=settings.STATIC_ROOT)
