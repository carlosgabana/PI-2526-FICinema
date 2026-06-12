from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario


class RegistroUsuarioForm(UserCreationForm):
    username = forms.CharField(
        required=True,
        label="Nombre de usuario",
        help_text="",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Elige un nombre de usuario",
            }
        ),
    )

    email = forms.EmailField(
        required=True,
        label="Correo electrónico",
        help_text="",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "ejemplo@correo.com",
            }
        ),
    )

    first_name = forms.CharField(
        required=False,
        label="Nombre",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "given-name",
                "placeholder": "Tu nombre",
            }
        ),
    )

    last_name = forms.CharField(
        required=False,
        label="Apellidos",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "family-name",
                "placeholder": "Tus apellidos",
            }
        ),
    )

    fechaNacimiento = forms.DateField(
        required=False,
        label="Fecha de nacimiento",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "max": date.today().isoformat(),
            }
        ),
    )

    genero = forms.ChoiceField(
        required=False,
        label="Género",
        choices=Usuario.GENERO_CHOICES,
    )

    password1 = forms.CharField(
        label="Contraseña",
        help_text="",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "password-input",
                "id": "id_password1",
                "placeholder": "Crea una contraseña segura",
            }
        ),
    )

    password2 = forms.CharField(
        label="Contraseña (confirmación)",
        help_text="",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "password-input",
                "id": "id_password2",
                "placeholder": "Repite la contraseña",
            }
        ),
    )

    class Meta:
        model = Usuario
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "fechaNacimiento",
            "genero",
            "password1",
            "password2",
        )

    def clean_username(self):
        username = self.cleaned_data.get("username")

        if username and Usuario.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ya existe un usuario con este nombre.")

        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if email and Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo electrónico.")

        return email

    def clean_fechaNacimiento(self):
        fecha = self.cleaned_data.get("fechaNacimiento")

        if fecha and fecha > date.today():
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura.")

        return fecha


class EditarPerfilForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "ejemplo@correo.com",
            }
        ),
    )

    first_name = forms.CharField(
        required=False,
        label="Nombre",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "given-name",
                "placeholder": "Tu nombre",
            }
        ),
    )

    last_name = forms.CharField(
        required=False,
        label="Apellidos",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "family-name",
                "placeholder": "Tus apellidos",
            }
        ),
    )

    fechaNacimiento = forms.DateField(
        required=False,
        label="Fecha de nacimiento",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "max": date.today().isoformat(),
            }
        ),
    )

    genero = forms.ChoiceField(
        required=False,
        label="Género",
        choices=Usuario.GENERO_CHOICES,
    )

    class Meta:
        model = Usuario
        fields = (
            "first_name",
            "last_name",
            "email",
            "fechaNacimiento",
            "genero",
        )

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if email and Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo electrónico.")

        return email

    def clean_fechaNacimiento(self):
        fecha = self.cleaned_data.get("fechaNacimiento")

        if fecha and fecha > date.today():
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura.")

        return fecha