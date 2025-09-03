from django.contrib import admin
from django.forms import ModelForm, PasswordInput

from .models import BetPage, Account


class AccountAdminForm(ModelForm):
    class Meta:
        model = Account
        fields = "__all__"
        widgets = {"password": PasswordInput(render_value=True)}


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    form = AccountAdminForm
    list_display = (
        "username",
        "bet_page",
        "email",
    )


@admin.register(BetPage)
class BetPageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "domain",
        "active",
    )
