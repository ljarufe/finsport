from django import forms

from django_countries.widgets import CountrySelectWidget

from football.models import League


class LeagueForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ('name', 'country')
        widgets = {'country': CountrySelectWidget()}
