from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def as_percent(value, digits=1):
    """Format a ratio as a percentage without changing metric semantics."""
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value) * 100:.{int(digits)}f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def yes_no_unknown(value):
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "—"


@register.filter
def value_or_dash(value):
    return "—" if value is None or value == "" else value


@register.filter
def as_units(value):
    if value is None or value == "":
        return "—"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    rendered = format(number.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return f"{rendered}u"
