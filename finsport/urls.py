from django.contrib import admin
from django.urls import path
from django.conf.urls import include, url
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('bet/', include('bet.urls', namespace="bet")),
    url('', RedirectView.as_view(
        pattern_name='bet:statistics', permanent=False)),
]
