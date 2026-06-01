"""
URL configuration for siprac project.
"""
from django.contrib import admin
from django.urls import path

from core.views import (
    DashboardView,
    EncaminhamentoCreateView,
    FinalidadesAPIView,
    OSCreateView,
    OSDetailView,
    OSListView,
    ProducaoCreateView,
    ProximoNumeroAPIView,
    SipracLoginView,
    SipracLogoutView,
    TiposDemandaAPIView,
)

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('login/', SipracLoginView.as_view(), name='login'),
    path('logout/', SipracLogoutView.as_view(), name='logout'),
    path('os/nova/', OSCreateView.as_view(), name='os_nova'),
    path('os/<int:pk>/encaminhar/', EncaminhamentoCreateView.as_view(), name='os_encaminhar'),
    path('os/<int:pk>/producao/', ProducaoCreateView.as_view(), name='os_producao'),
    path('os/<int:pk>/', OSDetailView.as_view(), name='os_detalhe'),
    path('os/', OSListView.as_view(), name='os_list'),
    path('api/tipos-demanda/', TiposDemandaAPIView.as_view(), name='api_tipos_demanda'),
    path('api/finalidades/', FinalidadesAPIView.as_view(), name='api_finalidades'),
    path('api/proximo-numero/', ProximoNumeroAPIView.as_view(), name='api_proximo_numero'),
    path('admin/', admin.site.urls),
]
