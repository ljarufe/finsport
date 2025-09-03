from django.urls import include, path
from rest_framework import routers

from .views import BetTableView

router = routers.DefaultRouter()
router.register(r"tables", BetTableView, basename="table")

urlpatterns = [
    path("", include(router.urls)),
]
