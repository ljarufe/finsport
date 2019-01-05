# -*- coding: utf-8 -*-
from django import template

from bet.constants import DICT_STATES_DATA_TABLE as states_datatable

register = template.Library()


@register.filter
def get_state(value):
    return states_datatable.get(value, '')


@register.filter
def roundd(value):
    return round(value, 2)


@register.filter
def fix_name_table(value):
    return value.split('.')[0]
