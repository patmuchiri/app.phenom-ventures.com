from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django.contrib.auth.models import Group
from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.db import  transaction, IntegrityError
import re
from .models import Payment, Client, Transaction, UserProfile, User
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# Kenyan phone number validator
kenyan_phone_validator = RegexValidator(
    regex=r'^(\+254|0)[17]\d{8}$',
    message="Enter a valid Kenyan phone number (e.g. +254712345678 or 0712345678)"
)

# ============== Authentication Forms ==============
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Username or Email'
        self.fields['password'].label = 'Password'

# ============== Client Forms ==============
class ClientAdminForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'
        widgets = {
            'client_type': forms.Select(attrs={'class': 'form-select'}),
            'contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+254...'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_account_name(self):
        account_name = self.cleaned_data.get('account_name')
        if not account_name:
            name = self.cleaned_data.get('name', '')
            account_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()[:20] or f"client{Client.objects.count() + 1}"
        return account_name

    def clean_contact(self):
        contact = self.cleaned_data.get('contact')
        if not re.match(r'^\+?[0-9]{10,15}$', contact):
            raise forms.ValidationError("Enter a valid phone number (10-15 digits, optional + prefix)")
        return contact

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'name',
            'account_name',
            'email',
            'contact',
            'ip_address',
            'package_name',
            'upload_limit',
            'download_limit',
            'package_price'
        ]
        widgets = {
            'client_type': forms.Select(attrs={'class': 'form-select'}),
            'contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+254...'
            }),
            'ip_address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '192.168.1.1'
            }),
            'package': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }

    def clean_account_name(self):
        account_name = self.cleaned_data.get('account_name')
        if not account_name:
            name = self.cleaned_data.get('name', '')
            account_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()[:20] or f"client{Client.objects.count() + 1}"
        return account_name

    def clean_contact(self):
        contact = self.cleaned_data.get('contact', '')
        if not contact:
            return contact
        
        # Remove all non-digit characters
        digits = re.sub(r'[^0-9]', '', contact)
    
        # Validate length
        if len(digits) < 10 or len(digits) > 15:
            raise forms.ValidationError(
                "Phone number must be 10-15 digits (after removing non-digit characters)"
            )
        return contact

# ============== User Management Forms ==============
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['designation', 'phone_number']
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+254712345678'
            }),
            'designation': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone_number'].validators = [kenyan_phone_validator]
        self.fields['phone_number'].help_text = "Format: +254712345678 or 0712345678"

class UserCreateForm(UserCreationForm):
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+254712345678'
        }),
        validators=[kenyan_phone_validator],
        help_text="Format: +254712345678 or 0712345678 (no spaces)",
        required=True
    )
    
    designation = forms.ChoiceField(
        choices=UserProfile.DESIGNATION_CHOICES,
        initial='support',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'designation',
            'is_active',
            'is_staff',
            'password1',
            'password2'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        self.fields['email'].required = True

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        if not phone:
            raise forms.ValidationError("Phone number is required")
        
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, phone))
        
        # Normalize phone number format
        if digits.startswith('0') and len(digits) == 10:
            return '+254' + digits[1:]
        elif digits.startswith('254') and len(digits) == 12:
            return '+' + digits
        elif digits.startswith('7') and len(digits) == 9:
            return '+254' + digits
        
        # If format doesn't match expected patterns, validator will catch it
        return phone

    def clean(self):
        cleaned_data = super().clean()
        # Add any cross-field validation here if needed
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Ensure we have normalized phone number
        phone_number = self.cleaned_data.get('phone_number')
        designation = self.cleaned_data.get('designation')
       
        if not phone_number:
            raise ValidationError("Phone number is required")
        
        if commit:
            try:
                with transaction.atomic():
                    user.save()
                    # Create profile with all required fields
                    UserProfile.objects.get_or_create(
                        user=user,
                        defaults={
                        'phone_number': phone_number,
                        'designation': designation
                        }
                    )
            except IntegrityError as e:
                logger.error(f"Database error creating user: {str(e)}")
                raise ValidationError("Could not create user profile due to database error")
            except Exception as e:
                logger.error(f"Unexpected error creating user: {str(e)}")
                raise ValidationError("An unexpected error occurred")
        
        return user


class SuperUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone_number')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone_number'].required = False

class UserEditForm(UserChangeForm):
    designation = forms.ChoiceField(
        choices=UserProfile.DESIGNATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='support',
        required=False
    )
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        validators=[kenyan_phone_validator]
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Remove password field if it exists
        if 'password' in self.fields:
            del self.fields['password']
        
        # Initialize profile fields
        if hasattr(self.instance, 'profile'):
            profile = self.instance.profile
            self.fields['designation'].initial = profile.designation
            self.fields['phone_number'].initial = profile.phone_number or self.instance.phone_number
  
    def clean(self):
        """Main clean method for cross-field validation"""
        cleaned_data = super().clean()
        return cleaned_data

    def save(self, commit=True):
        """Save user and profile data with proper transaction handling"""
        user = super().save(commit=False)
        phone_number = self.cleaned_data.get('phone_number')
        designation = self.cleaned_data.get('designation')
        
        if commit:
            try:
                with transaction.atomic():
                    user.save()
                    self.save_m2m()
                    
                    UserProfile.objects.update_or_create(
                        user=user,
                        defaults={
                            'phone_number': phone_number,
                            'designation': designation
                        }
                    )
                    
                    if phone_number and user.phone_number != phone_number:
                        user.phone_number = phone_number
                        user.save(update_fields=['phone_number'])
                    
            except Exception as e:
                logger.error(f"Error saving user: {str(e)}")
                raise ValidationError("Error saving user data")
        
        return user


# ============== Transaction Forms ==============
class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            'client',
            'transaction_type',
            'amount',
            'payment_method',
            'reference',
            'mpesa_code',
            'status',
            'notes'
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'mpesa_code': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = Client.objects.filter(is_active=True)
        self.fields['amount'].widget.attrs.update({'min': '0'})

class BulkPaymentForm(forms.Form):
    payment_file = forms.FileField(
        label='Payment CSV File',
        help_text='Upload a CSV file containing payment details',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        })
    )
    payment_method = forms.ChoiceField(
        choices=[
            ('MPESA', 'M-Pesa'),
            ('CASH', 'Cash'),
            ('BANK', 'Bank Transfer')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    transaction_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional payment description'
        })
    )
    
class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['client', 'amount', 'mpesa_code', 'status', 'notes']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'mpesa_code': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_payment_file(self):
        file = self.cleaned_data.get('payment_file')
        if file:
            if not file.name.endswith('.csv'):
                raise forms.ValidationError("Only CSV files are allowed")
        return file