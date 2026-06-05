from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(
        attrs={'placeholder': 'your@email.com', 'class': 'form-input'}
    ))
    name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(
        attrs={'placeholder': 'Display name (optional)', 'class': 'form-input'}
    ))

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'Choose a username', 'class': 'form-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Password (min 8 chars)', 'class': 'form-input'
        })
        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Confirm password', 'class': 'form-input'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.name  = self.cleaned_data.get('name', '')
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(
        attrs={'placeholder': 'Username', 'class': 'form-input', 'autofocus': True}
    ))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'placeholder': 'Password', 'class': 'form-input'}
    ))


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = CustomUser
        fields = ('name', 'email', 'avatar', 'bio')
        widgets = {
            'name':  forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'bio':   forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }