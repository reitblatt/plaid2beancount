# forms.py
from django import forms
from .models import Account

class TransactionFilterForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.all())
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))