from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class InscriptionForm(UserCreationForm):

    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    first_name = forms.CharField(
        required=True,
        label="Prénom",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        required=True,
        label="Nom",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'
        # ✅ Labels en français
        self.fields['password1'].label = "Mot de passe"
        self.fields['password2'].label = "Confirmer le mot de passe"
        # ✅ Supprimer les textes d'aide par défaut de Django
        self.fields['password1'].help_text = "Minimum 8 caractères."
        self.fields['password2'].help_text = ""

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet email.")
        return email

    def clean_first_name(self):
        return self.cleaned_data.get('first_name', '').strip().capitalize()

    def clean_last_name(self):
        return self.cleaned_data.get('last_name', '').strip().capitalize()

    def save(self, commit=True):
        user = super().save(commit=False)
        # ✅ Générer username depuis prénom + nom
        base     = f"{self.cleaned_data['first_name'].lower()}.{self.cleaned_data['last_name'].lower()}"
        base     = base.replace(' ', '')
        username = base
        counter  = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1
        user.username   = username
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.email      = self.cleaned_data['email']
        if commit:
            user.save()
        return user