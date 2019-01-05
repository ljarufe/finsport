from django.contrib import admin
from django.forms import ModelForm, PasswordInput

from .models import BetPage, Account


class AccountAdminForm(ModelForm):
    class Meta:
        model = Account
        fields = '__all__'
        widgets = {'password': PasswordInput(render_value=True),}


class AccountAdmin(admin.ModelAdmin):
    form = AccountAdminForm
    list_display = ('username', 'bet_page', 'funds', 'profit_to_tables',)


class BetPageAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain', 'match_list_url', 'active',)


admin.site.register(BetPage, BetPageAdmin)
admin.site.register(Account, AccountAdmin)
