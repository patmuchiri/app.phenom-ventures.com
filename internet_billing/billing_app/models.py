from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import IntegrityError 
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import re
import uuid
from decimal import Decimal
import decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import RegexValidator
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

kenyan_phone_validator = RegexValidator(
    regex=r'^(\+?254|0)?[17]\d{8}$',
    message="Enter a valid Kenyan phone number starting with +254, 254, 0, or 7 (e.g. +254712345678, 0712345678, 712345678)"
)

# ============== User Management Models ==============
class User(AbstractUser):
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[],
        help_text="Format: +254712345678 or 0712345678"
    )
    department = models.CharField(max_length=50, blank=True, null=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        permissions = [
            ('view_dashboard', 'Can view dashboard'),
            ('manage_users', 'Can manage users'),
            ('view_client', 'Can view client information'),
            ('add_client', 'Can add new client'),
            ('change_client', 'Can modify client information'),
            ('delete_client', 'Can delete client'),
            ('view_payment', 'Can view payment records'),
            ('add_payment', 'Can record new payment'),
            ('confirm_payment', 'Can confirm payments'),
            ('view_transaction', 'Can view transaction history'),
            ('add_transaction', 'Can create new transaction'),
            ('send_client_email', 'Can send email to client'),
            ('send_client_sms', 'Can send SMS to client'),
            ('send_bulk_sms', 'Can send bulk SMS to clients'),
            ('manage_network', 'Can manage network devices'),
        ]
    
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.email})"
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

    @property
    def is_accounting_staff(self):
        return self.has_perm('billing_app.add_payment')
    
    @property
    def is_support_staff(self):
        return self.has_perm('billing_app.add_client')


class UserProfile(models.Model):
    DESIGNATION_CHOICES = [
        ('admin', 'Administrator'),
        ('accountant', 'Accountant'),
        ('support', 'Support Staff'),
        ('technician', 'Network Technician'),
        ('manager', 'Manager'),
    ]
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    designation = models.CharField(
        max_length=50, 
        choices=DESIGNATION_CHOICES,
        default='support',
        blank=True,
        null=False,
        help_text="Select the user's role in the system"
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,  # Changed to allow blank temporarily
        null=True,   # Changed to allow null temporarily
        validators=[kenyan_phone_validator],
        help_text="Format: +254712345678, 0712345678, or 712345678"
    )
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                name='unique_user_profile'
            )
        ]
    
    def clean(self):
        """Simplified validation that only runs when phone_number is provided"""
        super().clean()
        
        if self.phone_number:  # Only validate if phone exists
            phone = ''.join(filter(str.isdigit, self.phone_number))
            
            # Standardize format
            if phone.startswith('0') and len(phone) == 10:
                self.phone_number = '+254' + phone[1:]
            elif phone.startswith('254') and len(phone) == 12:
                self.phone_number = '+' + phone
            elif phone.startswith('7') and len(phone) == 9:
                self.phone_number = '+254' + phone
            
            # Validate the standardized format
            kenyan_phone_validator(self.phone_number)
    
    def save(self, *args, **kwargs):
        """Only run full validation if phone_number is being set"""
        if self.phone_number:
            self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_designation_display()}"

@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Simplified signal handler that:
    1. Creates profile on user creation
    2. Doesn't force validation on permission updates
    """
    if created:
        try:
            UserProfile.objects.create(
                user=instance,
                designation='support',
                phone_number=instance.phone_number or '+254700000000'
            )
        except IntegrityError:
            # Profile already exists (race condition)
            pass
    elif not hasattr(instance, 'profile'):
        # Create profile if it was somehow missed
        UserProfile.objects.create(
            user=instance,
            designation='support',
            phone_number=instance.phone_number or '+254700000000'
        )

# ============== Bandwidth Package Models ==============
class BandwidthPackage(models.Model):
    name = models.CharField(max_length=50)
    speed_mbps = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=0, help_text="Higher number means higher priority")
    
    class Meta:
        ordering = ['-priority', 'name']
        permissions = [
            ('manage_bandwidthpackage', 'Can manage bandwidth packages'),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.speed_mbps}Mbps - KSh{self.price})"

# ============== Client Management Models ==============
class Client(models.Model):
    PACKAGE_CHOICES = [
        ('7mbps', 'Basic (7Mbps)'),
        ('10mbps', 'Standard (10Mbps)'),
        ('12mbps', 'Premium (12Mbps)'),
        ('14mbps', 'Business (14Mbps)'),
        ('15mbps', 'Premium Plus (15Mbps)'),
    ]
    
    PACKAGE_PRICES = {
        '7mbps': 1500,
        '10mbps': 2000,
        '12mbps': 2500,
        '14mbps': 3000,
        '15mbps': 4500,
    }
    
    name = models.CharField(max_length=100)
    account_name = models.CharField(
        max_length=50, 
        unique=True, 
        help_text="Unique name used for payment identification"
    )
    email = models.EmailField()
    contact = models.CharField(
        max_length=15,
        validators=[kenyan_phone_validator]
    )
    ip_address = models.CharField(max_length=15)
    package_name = models.CharField(max_length=20, choices=PACKAGE_CHOICES)
    upload_limit = models.CharField(max_length=10, default='10Mbps', help_text="Upload speed limit")
    download_limit = models.CharField(max_length=10, default='10Mbps', help_text="Download speed limit")
    package_price = models.DecimalField(max_digits=10, decimal_places=2)
    account_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('suspended', 'Suspended'),
        ],
        default='active'
    )
    deactivation_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='clients_created'
    )
    last_updated = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clients_updated'
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        permissions = [
            ('view_active_client', 'Can view active clients'),
            ('deactivate_client', 'Can deactivate clients'),
            ('activate_client', 'Can activate clients'),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.account_name})"
    
    def clean(self):
        # Validate account name format
        if not re.match(r'^[a-zA-Z0-9_-]+$', self.account_name):
            raise ValidationError(
                {'account_name': "Account name can only contain letters, numbers, underscores and hyphens"}
            )
        
        # Validate IP address format
        if self.ip_address and not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', self.ip_address):
            raise ValidationError(
                {'ip_address': "Enter a valid IP address (e.g., 192.168.1.1)"}
            )
    
    def save(self, *args, **kwargs):
        if not self.account_name:
            # Generate a default account name if not provided
            base_name = re.sub(r'[^a-zA-Z0-9]', '', self.name).lower()[:20]
            self.account_name = base_name or f"client{Client.objects.count() + 1}"
        
        # Ensure account name is unique
        counter = 1
        original_name = self.account_name
        while Client.objects.filter(account_name=self.account_name).exclude(pk=self.pk).exists():
            self.account_name = f"{original_name}{counter}"
            counter += 1
        
        # Set package price based on package name
        if self.package_name and not self.package_price:
            self.package_price = decimal.Decimal(self.PACKAGE_PRICES[self.package_name])
        
        # Update is_active based on status
        self.is_active = self.status == 'active'
        
        # Set deactivation date if being deactivated
        if self.status != 'active' and not self.deactivation_date:
            self.deactivation_date = timezone.now().date()
        
        # Update last_updated_by if available in kwargs
        if 'request_user' in kwargs:
            self.last_updated_by = kwargs.pop('request_user')
        
        super().save(*args, **kwargs)

    def get_balance(self):
        """Calculate current account balance from transactions"""
        payments = self.transactions.filter(
            transaction_type='PAYMENT',
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        adjustments = self.transactions.filter(
            transaction_type='ADJUSTMENT',
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        return payments + adjustments

# ============== Subscription Models ==============
class ClientSubscription(models.Model):
    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    package = models.ForeignKey(
        BandwidthPackage, 
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    #created_at = models.DateTimeField(default=timezone.now)  # Change from auto_now_add to default
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='subscriptions_created'
    )
    
    class Meta:
        ordering = ['-start_date']
        unique_together = [['client', 'package', 'start_date']]
        permissions = [
            ('manage_subscription', 'Can manage client subscriptions'),
        ]
    
    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.client.name} - {self.package.name} ({status})"
    
    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date")
        
        # Check for overlapping subscriptions
        overlapping = ClientSubscription.objects.filter(
            client=self.client,
            is_active=True,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date
        ).exclude(pk=self.pk).exists()
        
        if overlapping:
            raise ValidationError("Client already has an active subscription for this period")

    def days_remaining(self):
        """Calculate days remaining until subscription ends"""
        from django.utils.timezone import now
        if self.end_date < now().date():
            return 0
        return (self.end_date - now().date()).days

# ============== Transaction System Models ==============
class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('PAYMENT', 'Payment'),
        ('REFUND', 'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('SERVICE', 'Service Charge'),
    )
    
    PAYMENT_METHODS = (
        ('MPESA', 'M-Pesa'),
        ('CASH', 'Cash'),
        ('BANK', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    )
    
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REVERSED', 'Reversed'),
    )
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHODS,
        blank=True,
        null=True
    )
    reference = models.CharField(max_length=50, unique=True, blank=True)
    mpesa_code = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transactions_processed'
    )
    receipt_number = models.CharField(max_length=20, unique=True, blank=True)
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_approved'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-transaction_date']
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        permissions = [
            ('approve_transaction', 'Can approve transactions'),
            ('reverse_transaction', 'Can reverse transactions'),
        ]
    
    def __str__(self):
        return f"{self.client.name} - {self.get_transaction_type_display()} KSh{self.amount} ({self.get_status_display()})"
    
    def clean(self):
        if self.amount <= 0 and self.transaction_type in ['PAYMENT', 'ADJUSTMENT']:
            raise ValidationError({'amount': "Amount must be positive for payments and adjustments"})
        
        if self.transaction_type == 'REFUND' and self.amount >= 0:
            raise ValidationError({'amount': "Refund amount must be negative"})
    
    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate a unique reference number
            prefix = self.transaction_type[:3].upper()
            self.reference = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        
        if not self.receipt_number and self.status == 'COMPLETED':
            # Generate receipt number when transaction is completed
            self.receipt_number = f"RCPT-{self.transaction_date.strftime('%Y%m%d')}-{self.id:06d}"
        
        # Update client balance if this is a completed payment or adjustment
        if self.status == 'COMPLETED' and self.transaction_type in ['PAYMENT', 'ADJUSTMENT']:
            self.client.account_balance += self.amount
            self.client.save()
        
        super().save(*args, **kwargs)

# ============== Payment Models ==============
class Payment(models.Model):
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('partial', 'Partial'),
        ('overpaid', 'Overpaid'),
        ('failed', 'Failed'),
    )
    
    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_code = models.CharField(max_length=50, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    balance_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_confirmed'
    )
    confirmation_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_record'
    )
    receipt_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-payment_date']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        permissions = [
            ('verify_payment', 'Can verify payments'),
            ('process_bulk_payment', 'Can process bulk payments'),
        ]
    
    def __str__(self):
        return f"{self.client.name} - KSh{self.amount} ({self.get_status_display()})"
    
    def clean(self):
        if self.amount <= 0:
            raise ValidationError({'amount': "Payment amount must be positive"})
        
        if self.status == 'completed' and not self.confirmed_by:
            raise ValidationError("Completed payments must have a confirmation user")
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            # Generate a receipt number like "RCPT-2023-0001"
            year = self.payment_date.year
            last_payment = Payment.objects.filter(receipt_number__isnull=False).order_by('-id').first()
            if last_payment:
                last_num = int(last_payment.receipt_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.receipt_number = f"RCPT-{year}-{new_num:04d}"
        
        # Create associated transaction if this is a new payment
        if self.pk is None and self.status == 'completed':
            self.transaction = Transaction.objects.create(
                client=self.client,
                transaction_type='PAYMENT',
                amount=self.amount,
                payment_method='MPESA' if self.mpesa_code else 'CASH',
                reference=self.mpesa_code or self.receipt_number,
                status='COMPLETED',
                processed_by=self.confirmed_by,
                notes=f"Payment recorded via {'M-Pesa' if self.mpesa_code else 'manual entry'}"
            )
        
        super().save(*args, **kwargs)

# ============== Network Management Models ==============
class MikrotikRouter(models.Model):
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    username = models.CharField(max_length=50)
    password = models.CharField(max_length=100)
    api_port = models.PositiveIntegerField(default=8728)
    is_active = models.BooleanField(default=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        permissions = [
            ('sync_router', 'Can sync router configuration'),
            ('manage_router', 'Can manage router settings'),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.ip_address})"
    
    def clean(self):
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', self.ip_address):
            raise ValidationError({'ip_address': "Enter a valid IP address"})

# ============== Communication Models ==============
class SMSLog(models.Model):
    SMS_TYPES = (
        ('activation', 'Activation'),
        ('reminder', 'Reminder'),
        ('deactivation', 'Deactivation'),
        ('notification', 'Notification'),
        ('payment', 'Payment'),
        ('other', 'Other'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    )
    
    client = models.ForeignKey(
        Client, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='sms_logs'
    )
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sms_type = models.CharField(max_length=20, choices=SMS_TYPES, default='other')
    recipient_number = models.CharField(max_length=15, validators=[kenyan_phone_validator])
    cost = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_sent'
    )
    error_message = models.TextField(blank=True, null=True)
    external_id = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'SMS Log'
        verbose_name_plural = 'SMS Logs'
    
    def __str__(self):
        return f"{self.get_sms_type_display()} SMS to {self.recipient_number} ({self.get_status_display()})"

# ============== System Configuration Models ==============
class SystemConfig(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    last_modified = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_modified'
    )
    
    class Meta:
        verbose_name = 'System Configuration'
        verbose_name_plural = 'System Configurations'
        permissions = [
            ('manage_config', 'Can manage system configuration'),
        ]
    
    def __str__(self):
        return f"{self.key} = {self.value[:50]}"
    
    def clean(self):
        # Validate that sensitive configurations are not marked as public
        sensitive_keys = ['api_key', 'password', 'secret']
        if any(sk in self.key.lower() for sk in sensitive_keys) and self.is_public:
            raise ValidationError("Sensitive configuration keys cannot be marked as public")
