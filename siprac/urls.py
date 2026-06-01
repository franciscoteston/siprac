"""
URL configuration for siprac project.
"""
from django.contrib import admin
from django.urls import path

from core.views import DashboardView, SipracLoginView, SipracLogoutView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('login/', SipracLoginView.as_view(), name='login'),
    path('logout/', SipracLogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
]
