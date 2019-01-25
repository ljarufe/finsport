# -*- coding: utf-8 -*-

from django import template

register = template.Library()


# TODO: this filter is not longer necessary, delete it and change it for the
#  standard round with options
@register.filter
def roundd(value):
    return round(value, 2)


@register.filter
def fix_name_table(value):
    return value.split('.')[0]
