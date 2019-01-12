# -*- coding: utf-8 -*-

from dealer.git import git
from datetime import datetime, timedelta

from django.views.generic.list import ListView
from django.views.generic import TemplateView
from django.db.models import Sum

from bet.models import BetTable, DataTable
from bet.constants import (
    STATES_DATA_TABLE,
    TEAM_DIFFERENCE,
    MIN_PER_TEAM,
    MIN_PARITY,
)

COIN = 'S/'


class BetTableListView(ListView):

    model = BetTable

    def __init__(self, **kwargs):
        self.state = BetTable.FINISHED
        super(BetTableListView, self).__init__(**kwargs)

    # TODO: change the get parameter for the letter in the bettable dictionary
    def dispatch(self, request, *args, **kwargs):
        self.state = request.GET.get('state', 'finished')

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.filter(state=self.state).order_by('-created')

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        total_profit_tables = 0.0
        total_inversion_tables = 0.0
        total_inversion_tables_availables = 0.0
        num_tables = len(context['bettable_list'])

        for i, table in enumerate(context['bettable_list'], start=1):
            table.state = table.get_state_display()
            data_table = DataTable.objects.filter(
                bet_table=table).select_related(
                'match__local_team',
                'match__visitor_team').order_by('match__start_datetime')
            start = data_table.first().match.start_datetime
            end = data_table.last().match.start_datetime
            duration = (end - start)
            table.duration = '%s dias %s horas' % (
                duration.days, int(duration.seconds / 3600))
            table.data_table = data_table
            table.num = i
            total_profit_tables = round(
                total_profit_tables, 2) + table.total_profit
            if not table.total_inversion and data_table.exclude(
                    state=STATES_DATA_TABLE[0][0]):
                total_inversion_tables_availables += data_table.exclude(
                    state=STATES_DATA_TABLE[0][0]).last().inversion_amount
            total_inversion_tables += table.total_inversion
        context['total_profit_tables'] = round(total_profit_tables, 2)
        context['total_inversion_tables'] = (
            total_inversion_tables if total_inversion_tables else total_inversion_tables_availables)
        context['total_inversion_tables'] = round(
            context['total_inversion_tables'], 2)
        context['tables_state'] = self.state
        context['coin'] = COIN
        context['git_tag'] = git.tag
        context['num_tables'] = num_tables

        return context


class StatisticView(TemplateView):

    template_name = "bet/statistics.html"

    def dispatch(self, request, *args, **kwargs):
        self.time_state = request.GET.get('time-state', 'FT')

        return super().dispatch(request, *args, **kwargs)

    def results_by_time(self, context, time={}):
        w = ''
        if 'word' in time:
            w = '_%s' % time['word']
            time.pop('word')

        start_table = BetTable.objects.filter(**time).order_by('created')[:1]
        end_table = BetTable.objects.filter(**time).order_by('-created')[:1]
        time_simulation = timedelta(hours=0)
        context['coin'] = COIN
        context['time_simulation%s' % w] = time_simulation
        if start_table and end_table:
            time_simulation = (
                end_table.first().created - start_table.first().created)
            context['time_simulation%s' % w] = '%s días %s horas' % (
                time_simulation.days, int(time_simulation.seconds / 3600)
            )

        kw_state_tables = dict(state=BetTable.AVAILABLE)
        kw_state_tables.update(time)
        context['open_tables%s' % w] = BetTable.objects.filter(
            **kw_state_tables).count()
        kw_state_tables['state'] = BetTable.FINISHED
        context['finished_tables%s' % w] = BetTable.objects.filter(
            **kw_state_tables).count()
        kw_state_tables['state'] = BetTable.PAUSED
        context['paused_tables%s' % w] = BetTable.objects.filter(
            **kw_state_tables).count()

        total_inversion_amount = 0.0
        for table in BetTable.objects.filter(**time):
            data_table = DataTable.objects.filter(
                bet_table=table).select_related(
                'match__local_team',
                'match__visitor_team').order_by('match__start_datetime')
            try:
                total_inversion_amount += data_table.exclude(
                    state=STATES_DATA_TABLE[0][0]).last().inversion_amount
            except AttributeError:
                total_inversion_amount = 0
        context['total_inversion_amount%s' % w] = round(
            total_inversion_amount, 2)

        kw_total = dict(state=BetTable.FINISHED)
        kw_total.update(time)
        total_profit_dict = BetTable.objects.filter(
            **kw_total).aggregate(Sum('total_profit'))
        total_inversion_dict = BetTable.objects.filter(
            **kw_total).aggregate(Sum('total_inversion'))
        context['total_profit%s' % w] = total_profit_dict.get(
            'total_profit__sum', 0.0) if total_profit_dict.get(
            'total_profit__sum') else 0.0
        context['total_profit%s' % w] = round(context['total_profit%s' % w], 2)
        context['total_gross_profit%s' % w] = context[
            'total_profit%s' % w] + (total_inversion_dict.get(
                'total_inversion__sum', 0.0) if total_inversion_dict.get(
                'total_inversion__sum') else 0.0)
        context['total_gross_profit%s' % w] = round(
            context['total_gross_profit%s' % w], 2)
        context['profit_percentage%s' % w] = 0.0
        if total_inversion_amount:
            context['profit_percentage%s' % w] = round((context[
                'total_profit%s' % w] * 100) / total_inversion_amount, 2)

        return context

    # TODO: change everything, don't use while statement, use a query to fill the tables
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = self.results_by_time(context)
        iteration = 1
        data_finished_tables = {}
        while iteration <= 10:
            num_tables = 0
            net_profit = 0.0
            inversion = 0.0
            tables = BetTable.objects.filter(state=BetTable.FINISHED)
            for table in tables:
                num_datatables = DataTable.objects.filter(
                    bet_table=table).count()
                if iteration == num_datatables:
                    won_datatable = DataTable.objects.filter(
                        bet_table=table).order_by(
                        'match__start_datetime').last()
                    net_profit += (
                        won_datatable.profit - won_datatable.inversion_amount)
                    inversion += won_datatable.inversion_amount
                    num_tables = num_tables + 1
            try:
                percentage_inversion = (inversion * 100) / context[
                    'total_inversion_amount']
            except ZeroDivisionError:
                percentage_inversion = 0
            percentage_profit = (net_profit * 100) / context[
                'total_gross_profit'] if net_profit else 0
            data_finished_tables[iteration] = {
                'num_tables': round(num_tables, 2),
                'net_profit': round(net_profit, 2),
                'percentage_inversion': round(percentage_inversion, 2),
                'percentage_profit': round(percentage_profit, 2)
            }
            iteration = iteration + 1

        context['data_finished_tables'] = data_finished_tables

        from_date = datetime.now() - timedelta(days=2)
        context = self.results_by_time(
            context,
            time={'word': 'last_day', 'created__gt': from_date})
        from_date = datetime.now() - timedelta(days=8)
        context = self.results_by_time(
            context,
            time={'word': 'last_week', 'created__gt': from_date})
        from_date = datetime.now() - timedelta(days=31)
        context = self.results_by_time(
            context,
            time={'word': 'last_month', 'created__gt': from_date})
        context['team_difference'] = TEAM_DIFFERENCE
        context['min_per_team'] = MIN_PER_TEAM
        context['min_parity'] = MIN_PARITY
        context['git_tag'] = git.tag

        return context
