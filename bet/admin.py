from django.contrib import admin

from .models import BetTable, BetRow


class DataTableInline(admin.TabularInline):
    model = BetRow
    extra = 0
    ordering = ("created",)


@admin.register(BetTable)
class BetTableAdmin(admin.ModelAdmin):
    list_display = ('created', 'state', 'total_inversion', 'total_profit')
    list_filter = ('created', 'state')
    inlines = [DataTableInline]


@admin.register(BetRow)
class BetRowAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'state')
