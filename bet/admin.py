from django.contrib import admin

from .models import BetTable, BetRow


class BetRowInline(admin.StackedInline):
    model = BetRow
    extra = 0
    ordering = ("created",)
    raw_id_fields = ("match", "previous",)


@admin.register(BetTable)
class BetTableAdmin(admin.ModelAdmin):
    list_display = (
        'created', 'state', 'bucle_number', 'total_inversion', 'total_profit',)
    list_filter = ('created', 'state', 'bucle_number',)
    inlines = [BetRowInline]


@admin.register(BetRow)
class BetRowAdmin(admin.ModelAdmin):
    list_display = (
        'match', 'bet_table', 'state', 'bet_amount', 'profit',)
    list_filter = ('state', 'iteration',)
    search_fields = ('match__local_team__name', 'match__visitor_team__name',)
    raw_id_fields = ("match", "previous",)
