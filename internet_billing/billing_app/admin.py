from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils.http import urlencode
from .models import (
    Client, BandwidthPackage, UserProfile, ClientSubscription, Transaction, User,
    Payment, MikrotikRouter, SMSLog, SystemConfig
)
from .forms import ClientAdminForm, UserCreateForm, SuperUserCreationForm, UserEditForm, UserProfileForm

User = get_user_model()

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    form = UserProfileForm
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    max_num = 1
    fields = ('designation', 'phone_number')

class CustomUserAdmin(UserAdmin):
    form = UserEditForm
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    filter_horizontal = ('groups', 'user_permissions',)

    
    fieldsets = (
        (None, {'fields': ('username',)}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'department')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important Dates', {'fields': ('last_login', 'date_joined', 'last_activity')}),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Save the user and handle profile data
        """
        # First save the user
        super().save_model(request, obj, form, change)
        
        # Get or create profile
        profile, created = UserProfile.objects.get_or_create(user=obj)
        
        # Update profile fields only if they exist in form data
        if 'designation' in form.cleaned_data:
            profile.designation = form.cleaned_data['designation'] or 'support'  # Default value
        if 'phone_number' in form.cleaned_data:
            profile.phone_number = form.cleaned_data['phone_number']
            
        # Skip full validation when only permissions are being updated
        if not any(field in form.changed_data for field in ['designation', 'phone_number']):
            profile.save(update_fields=['designation', 'phone_number'], validate=False)
        else:
            profile.save()
        

# Register the custom admin
admin.site.register(User, CustomUserAdmin)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    form = ClientAdminForm
    list_display = ('name', 'account_name', 'contact', 'email', 'ip_address', 
                   'package_name', 'created_at')
    list_filter = ('package_name', 'created_at')
    search_fields = ('name', 'account_name', 'contact', 'email', 'ip_address')
    list_per_page = 50
    actions = ['activate_clients', 'deactivate_clients']
    readonly_fields = ('created_at',)  # Removed non-existent fields
    
    def activate_clients(self, request, queryset):
        if hasattr(Client, 'is_active'):
            queryset.update(is_active=True)
            self.message_user(request, f"{queryset.count()} clients activated")
        else:
            self.message_user(request, "Client model has no is_active field", level='error')
    
    def deactivate_clients(self, request, queryset):
        if hasattr(Client, 'is_active'):
            queryset.update(is_active=False)
            self.message_user(request, f"{queryset.count()} clients deactivated")
        else:
            self.message_user(request, "Client model has no is_active field", level='error')
    
    activate_clients.short_description = "Activate selected clients"
    deactivate_clients.short_description = "Deactivate selected clients"    
    
    def subscriptions_count(self, obj):
        count = obj.subscriptions.count()
        url = reverse('admin:billing_app_clientsubscription_changelist') + '?' + urlencode({'client__id': obj.id})
        return format_html('<a href="{}">{} Subscriptions</a>', url, count)
    subscriptions_count.short_description = 'Subscriptions'

    def payments_count(self, obj):
        count = obj.payments.count()
        url = reverse('admin:billing_app_payment_changelist') + '?' + urlencode({'client__id': obj.id})
        return format_html('<a href="{}">{} Payments</a>', url, count)
    payments_count.short_description = 'Payments'

    @admin.action(description='Activate selected clients')
    def activate_clients(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} clients activated')

    @admin.action(description='Deactivate selected clients')
    def deactivate_clients(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} clients deactivated')

@admin.register(BandwidthPackage)
class BandwidthPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'speed_mbps', 'price', 'is_active', 'subscriptions_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    list_editable = ('is_active', 'price')
    ordering = ('-priority', 'name')
    
    def subscriptions_count(self, obj):
        count = obj.subscriptions.count()
        url = reverse('admin:billing_app_clientsubscription_changelist') + '?' + urlencode({'package__id': obj.id})
        return format_html('<a href="{}">{} Subscribers</a>', url, count)
    subscriptions_count.short_description = 'Subscribers'

@admin.register(ClientSubscription)
class ClientSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('client', 'package', 'start_date', 'end_date', 'days_remaining', 'is_active', 'auto_renew')
    list_filter = ('is_active', 'package', 'start_date', 'auto_renew')
    search_fields = ('client__name', 'package__name')
    date_hierarchy = 'start_date'
    raw_id_fields = ('client',)
    list_select_related = ('client', 'package')
    readonly_fields = ()  # Removed non-existent fields
    
    def days_remaining(self, obj):
        from django.utils.timezone import now
        if obj.end_date < now().date():
            return format_html('<span style="color: red;">Expired</span>')
        days = (obj.end_date - now().date()).days
        color = 'red' if days <= 7 else 'green'
        return format_html('<span style="color: {};">{} days</span>', color, days)
    days_remaining.short_description = 'Days Left'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('mpesa_code', 'client', 'amount', 'payment_date', 'status', 'confirmed_by', 'confirmation_date')
    list_filter = ('status', 'payment_date')  # Removed payment_method if it's not a field
    search_fields = ('client__name', 'mpesa_code', 'client__account_name', 'client__contact')
    date_hierarchy = 'payment_date'
    raw_id_fields = ('client', 'confirmed_by')
    list_select_related = ('client', 'confirmed_by')
    readonly_fields = ('payment_date',)  # Removed non-existent fields
    actions = ['mark_as_completed', 'mark_as_failed']
    
    @admin.action(description='Mark selected payments as completed')
    def mark_as_completed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            status='completed',
            confirmed_by=request.user,
            confirmation_date=timezone.now()
        )
        self.message_user(request, f'{updated} payments marked as completed')

    @admin.action(description='Mark selected payments as failed')
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status='failed')
        self.message_user(request, f'{updated} payments marked as failed')

@admin.register(MikrotikRouter)
class MikrotikRouterAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip_address', 'api_port', 'is_active', 'last_sync')
    list_filter = ('is_active',)
    search_fields = ('name', 'ip_address', 'location')
    exclude = ('password',)
    readonly_fields = ('last_sync',)  # Removed non-existent fields
    
    def save_model(self, request, obj, form, change):
        if 'password' in form.changed_data:
            # Password was changed - encrypt it here if needed
            pass
        super().save_model(request, obj, form, change)

@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ('sent_at', 'recipient_number', 'sms_type', 'client', 'status', 'cost')
    list_filter = ('sms_type', 'status', 'sent_at')
    search_fields = ('client__name', 'recipient_number', 'message', 'client__account_name')
    date_hierarchy = 'sent_at'
    raw_id_fields = ('client',)
    readonly_fields = ('sent_at',)  # Removed non-existent fields
    list_select_related = ('client',)

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('key', 'value_short', 'description', 'last_modified')
    search_fields = ('key', 'value', 'description')
    readonly_fields = ('last_modified',)  # Removed non-existent fields
    
    def value_short(self, obj):
        return obj.value[:50] + '...' if len(obj.value) > 50 else obj.value
    value_short.short_description = 'Value'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'designation', 'phone_number')
    search_fields = ('user__username', 'user__email', 'phone_number')

# Custom admin site settings
admin.site.site_header = "Phenom Ventures Ltd - Billing System Administration"
admin.site.site_title = "Phenom Billing System"
admin.site.index_title = "Welcome to Phenom Billing System"