from django.contrib import admin

from .models import BetTable, BetRow


class DataTableInline(admin.TabularInline):

    model = BetRow
    extra = 0
    ordering = ("created", )


class BetTableAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'created',
        'state',
        'total_inversion',
        'total_profit',
    )

    list_filter = ('created', 'state')

    inlines = [DataTableInline, ]


class DataTableAdmin(admin.ModelAdmin):

    list_display = (
        '__str__',
        'state'
    )


admin.site.register(BetTable, BetTableAdmin)
admin.site.register(BetRow, DataTableAdmin)
