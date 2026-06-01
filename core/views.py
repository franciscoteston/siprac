from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from core.mixins import RequerLoginMixin


class SipracLoginView(LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard")


class SipracLogoutView(LogoutView):
    next_page = reverse_lazy("login")


class DashboardView(RequerLoginMixin, TemplateView):
    template_name = "dashboard.html"
