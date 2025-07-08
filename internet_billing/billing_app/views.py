from django.shortcuts import render, redirect, get_object_or_404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.urls.resolvers import get_resolver
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, FloatField
from django.db.models.functions import TruncMonth
from django.db.models.expressions import ExpressionWrapper
from django.db.models.fields import FloatField
from django.core.mail import EmailMessage
from io import BytesIO
from django.core.mail import send_mail
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import Payment
from reportlab.lib.pagesizes import letter
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import Group, User
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from django.views.generic import (
    CreateView, UpdateView, ListView, 
    DeleteView, DetailView
)
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
import json
import csv
import logging
from billing_app.models import Client
from datetime import datetime, timedelta
from .models import (
    Client, ClientSubscription, Payment, UserProfile,
    SMSLog, Transaction
)
from .forms import (
    ClientForm, UserCreateForm, UserEditForm,
    TransactionForm, BulkPaymentForm, LoginForm,
    PaymentForm
)
from .mpesa import MpesaGateway
from .sms import SMSManager
from .routeros_api import configure_mikrotik_queue

logger = logging.getLogger(__name__)

# ============== Authentication Views ==============
class LoginView(View):
    form_class = LoginForm
    template_name = 'billing_app/login.html' 

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
        messages.error(request, "Invalid username or password")
        return render(request, self.template_name, {'form': form})

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')

# ============== Core Views ==============
def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'billing_app/home.html')

@login_required
def landing(request):
    return render(request, 'billing_app/landing.html')

# ============== Client Management Views ==============
class ClientListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Client
    template_name = 'billing_app/client_list.html'
    context_object_name = 'clients'
    paginate_by = 20
    permission_required = 'billing_app.view_client'
    recent_clients = Client.objects.all().order_by('-created_at')[:5]
    
    def get_queryset(self):
        queryset = super().get_queryset().order_by('name')
        search_query = self.request.GET.get('q', '')
        package_filter = self.request.GET.get('package', '')

        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(account_name__icontains=search_query) |
                Q(contact__icontains=search_query) |
                Q(ip_address__icontains=search_query)
        )       
        if package_filter:
            queryset = queryset.filter(package_name=package_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['package_filter'] = self.request.GET.get('package', '')
        return context
        
        
class ClientDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Client
    template_name = 'billing_app/client_detail.html'
    permission_required = 'billing_app.view_client'
    context_object_name = 'client'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_object()
        context['subscriptions'] = client.subscriptions.all().order_by('-start_date')
        context['payments'] = client.payments.all().order_by('-payment_date')
        context['transactions'] = client.transactions.all().order_by('-transaction_date')[:10]
        return context

class ClientCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'billing_app/client_form.html'
    permission_required = 'billing_app.add_client'
    success_url = reverse_lazy('client_list')

    def form_valid(self, form):
        client = form.save()
        
        if client.ip_address and client.package_name:
            if configure_mikrotik_queue(client):
                messages.success(self.request, "MikroTik queue configured successfully!")
            else:
                messages.warning(self.request, "Client created but MikroTik configuration failed")
        
        sms = SMSManager()
        sms.send_sms(
            client.contact,
            f"Dear {client.name}, your {client.package_name} package has been activated. "
            f"IP: {client.ip_address}, Speed: {client.download_limit} down / {client.upload_limit} up. "
            f"Pay via M-PESA Paybill {settings.MPESA_BUSINESS_SHORTCODE} "
            f"Account {client.account_name}"
        )
        
        messages.success(self.request, f"Client {client.name} created successfully!")
        return super().form_valid(form)

class ClientUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'billing_app/client_form.html'
    permission_required = 'billing_app.change_client'
    success_url = reverse_lazy('client_list')

    def form_valid(self, form):
        client = form.save()
        
        # Update MikroTik queue if IP or package changed
        if form.has_changed() and ('ip_address' in form.changed_data or 'package_name' in form.changed_data):
            if client.ip_address and client.package_name:
                if configure_mikrotik_queue(client):
                    messages.success(self.request, "MikroTik queue updated successfully!")
                else:
                    messages.warning(self.request, "Client updated but MikroTik configuration failed")
        
        messages.success(self.request, f"Client {client.name} updated successfully!")
        return super().form_valid(form)

class ClientDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Client
    template_name = 'billing_app/client_confirm_delete.html'
    permission_required = 'billing_app.delete_client'
    success_url = reverse_lazy('client_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = self.get_object()
        return context

@login_required
@permission_required('billing_app.change_client', raise_exception=True)
def client_toggle_status(request, pk):
    client = get_object_or_404(Client, pk=pk)
    client.is_active = not client.is_active
    client.save()
    
    # Configure MikroTik based on status
    if client.ip_address and client.package_name:
        if client.is_active:
            if configure_mikrotik_queue(client):
                message = f"activated with {client.download_limit} down / {client.upload_limit} up speed"
            else:
                client.is_active = False
                client.save()
                messages.warning(request, "MikroTik configuration failed!")
                return redirect('client_detail', pk=client.pk)
        else:
            # Deactivate in MikroTik (implementation needed in routeros_api.py)
            if configure_mikrotik_queue(client, activate=False):
                message = "deactivated"
            else:
                messages.warning(request, "MikroTik deactivation failed!")
    
    # SMS notification
    sms = SMSManager()
    sms.send_sms(
        client.contact,
        f"Dear {client.name}, your internet has been {message}. "
        f"Contact {settings.COMPANY_CONTACT} for queries."
    )
    
    messages.success(request, f"Client {client.name} {message} successfully!")
    return redirect('client_detail', pk=client.pk)

@login_required
def client_quick_search(request):
    query = request.GET.get('q', '')
    if query:
        clients = Client.objects.filter(
            Q(name__icontains=query) |
            Q(account_name__icontains=query) |
            Q(contact__icontains=query) |
            Q(ip_address__icontains=query)
        ).order_by('name')[:10]
        results = [{
            'id': client.id,
            'text': f"{client.name} ({client.account_name}) - {client.contact}"
        } for client in clients]
    else:
        results = []
    return JsonResponse({'results': results})

@login_required
@permission_required('billing_app.process_payment', raise_exception=True)
def manual_payment_processing(request, client_pk=None):
    client = None
    if client_pk:
        client = get_object_or_404(Client, pk=client_pk)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)  # Using PaymentForm
        if form.is_valid():
            payment = form.save(commit=False)
            payment.processed_by = request.user
            if client:
                payment.client = client
            payment.save()
            
            # Update client balance
            if client:
                client.account_balance += payment.amount
                client.save()
            
            messages.success(request, "Payment recorded successfully!")
            return redirect('client_detail', pk=client.pk if client else payment.client.pk)
    else:
        initial = {'client': client.id} if client else {}
        form = PaymentForm(initial=initial)  # Using PaymentForm
    
    context = {
        'form': form,
        'client': client,
    }
    return render(request, 'billing_app/manual_payment.html', context)
    
@login_required
@permission_required('billing_app.send_client_email', raise_exception=True)
def send_client_email(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        
        if not subject or not message:
            messages.error(request, "Both subject and message are required")
            return redirect('client_detail', pk=client.pk)
        
        try:
            send_mail(
                subject,
                message,
                'billing@phenom-ventures.com',
                [client.email],
                fail_silently=False,
            )
            messages.success(request, f"Email successfully sent to {client.name}")
        except Exception as e:
            messages.error(request, f"Failed to send email: {str(e)}")
        
        return redirect('client_detail', pk=client.pk)
    
def send_client_sms(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        message = request.POST.get('message')
        sms = SMSManager()
        sms.send_sms(client.contact, message)
        
        messages.success(request, f"SMS sent to {client.name}")
        return redirect('client_detail', pk=client.pk)
    return redirect('client_detail', pk=client.pk)


# ============== User Management Views ==============
User = get_user_model()

class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = User
    template_name = 'billing_app/user_list.html'
    context_object_name = 'users'
    permission_required = 'billing_app.view_user'
    ordering = ['last_name', 'first_name']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profiles'] = UserProfile.objects.select_related('user')
        return context

class UserCreateView(CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'billing_app/user_form.html'
    success_url = reverse_lazy('user_list')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(self.request, 'User created successfully!')
            return response
        except ValidationError as e:
            form.add_error(None, e)
            messages.error(self.request, 'Please correct the errors below')
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            messages.error(self.request, 'An error occurred while creating the user')
            return self.form_invalid(form)

class UserUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'billing_app/user_form.html'
    permission_required = 'billing_app.change_user'
    success_url = reverse_lazy('user_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"User {self.object.username} updated successfully!")
        return response

class UserDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = User
    template_name = 'billing_app/user_confirm_delete.html'
    permission_required = 'billing_app.delete_user'
    success_url = reverse_lazy('user_list')

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"User {user.username} deleted successfully!")
        return response

class UserPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'billing_app/change_password.html'
    success_url = reverse_lazy('billing_app:user_list')  # Use your app namespace

# ============== Transaction Views ==============
class TransactionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Transaction
    template_name = 'billing_app/transaction_list.html'
    context_object_name = 'transactions'
    permission_required = 'billing_app.view_transaction'
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset().order_by('-transaction_date')
        transaction_type = self.request.GET.get('type', '')
        status = self.request.GET.get('status', '')
        date_range = self.request.GET.get('date_range', '')

        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        if status:
            queryset = queryset.filter(status=status)
        if date_range:
            if date_range == 'today':
                queryset = queryset.filter(transaction_date__date=datetime.now().date())
            elif date_range == 'week':
                start_date = datetime.now() - timedelta(days=7)
                queryset = queryset.filter(transaction_date__gte=start_date)
            elif date_range == 'month':
                start_date = datetime.now() - timedelta(days=30)
                queryset = queryset.filter(transaction_date__gte=start_date)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_type'] = self.request.GET.get('type', '')
        context['status'] = self.request.GET.get('status', '')
        context['date_range'] = self.request.GET.get('date_range', '')
        return context

class TransactionCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'billing_app/transaction_form.html'
    permission_required = 'billing_app.add_transaction'

    def form_valid(self, form):
        transaction = form.save(commit=False)
        transaction.processed_by = self.request.user
        transaction.save()
        
        if transaction.transaction_type in ['PAYMENT', 'ADJUSTMENT']:
            client = transaction.client
            client.account_balance += transaction.amount
            client.save()
            
            if transaction.transaction_type == 'PAYMENT':
                sms = SMSManager()
                sms.send_sms(
                    client.contact,
                    f"Payment of KES {transaction.amount} received. "
                    f"New balance: KES {client.account_balance}. "
                    f"Ref: {transaction.reference}"
                )
        
        # Check if "Save and Email" was clicked
        if 'save_and_email' in self.request.POST:
            return self.generate_pdf_and_email(transaction)
        
        messages.success(self.request, "Transaction recorded successfully!")
        return super().form_valid(form)

    def generate_pdf_and_email(self, transaction):
        # Generate PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        # PDF content
        p.drawString(100, 750, "PHENOM VENTURES - PAYMENT RECEIPT")
        p.drawString(100, 730, f"Receipt No: {transaction.reference}")
        p.drawString(100, 710, f"Date: {transaction.transaction_date.strftime('%Y-%m-%d %H:%M')}")
        p.drawString(100, 690, f"Client: {transaction.client.name}")
        p.drawString(100, 670, f"Amount: KES {transaction.amount:.2f}")
        p.drawString(100, 650, f"Payment Method: {transaction.get_payment_method_display()}")
        p.drawString(100, 630, f"Processed By: {transaction.processed_by.username}")
        
        p.showPage()
        p.save()
        
        pdf = buffer.getvalue()
        buffer.close()
        
        # Create email with PDF attachment
        email = EmailMessage(
            subject=f"Payment Receipt - {transaction.reference}",
            body=f"Dear {transaction.client.name},\n\nPlease find attached your payment receipt.\n\n"
                 f"Amount: KES {transaction.amount:.2f}\n"
                 f"Reference: {transaction.reference}\n\n"
                 "Thank you for your business!\n\n"
                 "Phenom Ventures Billing Department",
            from_email="billing@phenom-ventures.com",
            to=[transaction.client.email],
            cc=["billing@phenom-ventures.com"],
        )
        email.attach(f"receipt_{transaction.reference}.pdf", pdf, "application/pdf")
        
        # For opening default mail client (frontend will handle actual sending)
        mailto_url = f"mailto:{transaction.client.email}?" \
                    f"subject=Payment Receipt - {transaction.reference}&" \
                    f"body=Dear {transaction.client.name}%2C%0A%0APlease find attached your payment receipt.%0A%0A" \
                    f"Amount%3A KES {transaction.amount:.2f}%0A" \
                    f"Reference%3A {transaction.reference}%0A%0A" \
                    "Thank you for your business!%0A%0A" \
                    "Phenom Ventures Billing Department" \
                    "&cc=billing@phenom-ventures.com"
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="receipt_{transaction.reference}.pdf"'
        response.write(pdf)
        
        # Return both the PDF and mailto URL
        return JsonResponse({
            'pdf_url': reverse('transaction_detail', kwargs={'pk': transaction.pk}),
            'mailto_url': mailto_url,
            'success_url': reverse('transaction_detail', kwargs={'pk': transaction.pk})
        })

    def get_success_url(self):
        return reverse_lazy('transaction_detail', kwargs={'pk': self.object.pk})

class TransactionDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Transaction
    template_name = 'billing_app/transaction_detail.html'
    permission_required = 'billing_app.view_transaction'
    context_object_name = 'transaction'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_email_receipt'] = self.object.transaction_type == 'PAYMENT'
        return context
        # Add payment details if available
        if hasattr(self.object, 'payment_record'):
            context['payment'] = self.object.payment_record
        return context

class TransactionUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'billing_app/transaction_form.html'
    permission_required = 'billing_app.change_transaction'

    def form_valid(self, form):
        transaction = form.save()
        
        # Update client balance if payment or adjustment
        if transaction.transaction_type in ['PAYMENT', 'ADJUSTMENT']:
            client = transaction.client
            # You might want to implement a more robust balance update logic here
            client.account_balance = client.transactions.aggregate(
                Sum('amount')
            )['amount__sum'] or 0
            client.save()
        
        messages.success(self.request, "Transaction updated successfully!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('transaction_detail', kwargs={'pk': self.object.pk})
        
class BulkPaymentView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'billing_app.process_bulk_payment'
    template_name = 'billing_app/bulk_payment.html'
    form_class = BulkPaymentForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        if form.is_valid():
            # Process the bulk payment file (CSV/Excel)
            file = request.FILES['payment_file']
            # Implement your bulk payment processing logic here
            
            messages.success(request, "Bulk payments processed successfully!")
            return redirect('transaction_list')
        return render(request, self.template_name, {'form': form})

def transaction_receipt_pdf(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    
    # Create PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # PDF content
    p.drawString(100, 750, "PHENOM VENTURES - PAYMENT RECEIPT")
    p.drawString(100, 730, f"Receipt No: {transaction.reference}")
    p.drawString(100, 710, f"Date: {transaction.transaction_date.strftime('%Y-%m-%d %H:%M')}")
    p.drawString(100, 690, f"Client: {transaction.client.name}")
    p.drawString(100, 670, f"Amount: KES {transaction.amount:.2f}")
    p.drawString(100, 650, f"Payment Method: {transaction.get_payment_method_display()}")
    p.drawString(100, 630, f"Processed By: {transaction.processed_by.username}")
    
    p.showPage()
    p.save()
    
    # Get PDF value
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{transaction.reference}.pdf"'
    response.write(pdf)
    return response

@login_required
def financial_reports(request):
    # Get view type and period from request
    view_type = request.GET.get('view', 'list')  # Default to list view
    period = request.GET.get('period', 'daily')  # Default to daily
    
    today = datetime.now().date()
    summary_data = []
    totals = {'count': 0, 'amount': 0}
    
    # Define date ranges based on period
    if period == 'daily':
        start_date = today
        transactions = Transaction.objects.filter(transaction_date__date=today)
    elif period == 'monthly':
        start_date = today - timedelta(days=30)
        transactions = Transaction.objects.filter(transaction_date__date__gte=start_date)
    elif period == '3months':
        start_date = today - timedelta(days=90)
        transactions = Transaction.objects.filter(transaction_date__date__gte=start_date)
    elif period == '6months':
        start_date = today - timedelta(days=180)
        transactions = Transaction.objects.filter(transaction_date__date__gte=start_date)
    elif period == 'yearly':
        start_date = today - timedelta(days=365)
        transactions = Transaction.objects.filter(transaction_date__date__gte=start_date)
    else:
        start_date = today
        transactions = Transaction.objects.filter(transaction_date__date=today)
    
    # Aggregate data by transaction type
    summary = transactions.values('transaction_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    ).order_by('-total_amount')
    
    # Calculate totals and percentages
    total_amount = sum(item['total_amount'] for item in summary)
    for item in summary:
        percentage = (item['total_amount'] / total_amount * 100) if total_amount > 0 else 0
        summary_data.append({
            'transaction_type': item['transaction_type'],
            'count': item['count'],
            'total_amount': item['total_amount'],
            'percentage': percentage
        })
        totals['count'] += item['count']
        totals['amount'] += item['total_amount']
    
    context = {
        'summary_data': summary_data,
        'totals': totals,
        'period': period,
        'view_type': view_type,
        'today': today,
        'start_date': start_date,
    }
    return render(request, 'billing_app/financial_reports.html', context)

# ============== Dashboard Views ==============
@login_required
def dashboard(request):
    # Get the custom User model
    User = get_user_model()
    
    # Client statistics
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(is_active=True).count()
    inactive_clients = total_clients - active_clients
    
    # Package distribution
    package_distribution = Client.objects.values('package_name').annotate(
        count=Count('id'),
        percentage=ExpressionWrapper(
            Count('id') * 100.0 / total_clients,
            output_field=FloatField()
        )
    ).order_by('-count')
    
    # Payment statistics
    today = datetime.now().date()
    today_payments = Transaction.objects.filter(
        transaction_date__date=today,
        transaction_type='PAYMENT'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    monthly_payments = Transaction.objects.filter(
        transaction_date__date__gte=today - timedelta(days=30),
        transaction_type='PAYMENT'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    pending_payments = Payment.objects.filter(status='pending').count()
    
    # Recent activity
    recent_transactions = Transaction.objects.all().order_by('-transaction_date')[:5]
    recent_clients = Client.objects.all().order_by('-created_at')[:5]
    
    # User management data - using select_related with the correct related_name
    users = User.objects.select_related('profile').all().order_by('-date_joined')[:10]
    user_count = User.objects.count()
    
    # Get designation choices for the add user form
    user_profile_designations = UserProfile.DESIGNATION_CHOICES
    
    # Prepare user data with profile information
    user_data = []
    for user in users:
        user_data.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'email': user.email,
            'designation': user.profile.designation if hasattr(user, 'profile') else 'Not specified',
            'phone_number': user.profile.phone_number if hasattr(user, 'profile') else 'Not provided',
            'date_joined': user.date_joined
        })
    
    context = {
        # Client statistics
        'total_clients': total_clients,
        'active_clients': active_clients,
        'inactive_clients': inactive_clients,
        
        # Package information
        'package_distribution': package_distribution,
        
        # Financial data
        'today_payments': today_payments,
        'monthly_payments': monthly_payments,
        'pending_payments': pending_payments,
        
        # Recent activity
        'recent_transactions': recent_transactions,
        'recent_clients': recent_clients,
        
        # User management
        'users': users,  # Pass the User queryset directly
        'user_data': user_data,  # Pass the processed user data
        'user_count': user_count,
        'user_profile_designations': user_profile_designations,
    }
    
    return render(request, 'billing_app/dashboard.html', context)
    

class MpesaCallbackView(View):
    def post(self, request, *args, **kwargs):
        try:
            # Parse the M-Pesa callback data
            data = json.loads(request.body)
            
            # Process the payment callback
            # Example: Update payment status based on M-Pesa response
            mpesa_code = data.get('TransID')
            amount = data.get('TransAmount')
            phone = data.get('MSISDN')
            
            # Find and update the payment record
            payment = Payment.objects.filter(mpesa_code=mpesa_code).first()
            if payment:
                payment.status = 'completed'
                payment.save()
                
                # Update client balance or perform other actions
                client = payment.client
                client.account_balance += float(amount)
                client.save()
            
            return HttpResponse(status=200)
            
        except Exception as e:
            # Log the error for debugging
            print(f"M-Pesa callback error: {str(e)}")
            return HttpResponse(status=400)
         
# ============== Payment Views ==============
class PaymentFormView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Handles both display and processing of payment form"""
    permission_required = 'billing_app.process_payment'
    template_name = 'billing_app/payment_form.html'
    form_class = PaymentForm  # Using the form from forms.py

    def get(self, request, client_pk=None):
        client = None
        if client_pk:
            client = get_object_or_404(Client, pk=client_pk)
        
        form = self.form_class(initial={'client': client.id} if client else None)
        return render(request, self.template_name, {
            'form': form,
            'client': client,
        })

    def post(self, request, client_pk=None):
        client = None
        if client_pk:
            client = get_object_or_404(Client, pk=client_pk)
        
        form = self.form_class(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.processed_by = request.user
            if client:
                payment.client = client
            payment.save()
            
            # Update client balance
            if client:
                client.account_balance += payment.amount
                client.save()
            
            messages.success(request, "Payment recorded successfully!")
            return redirect('client_detail', pk=client.pk if client else payment.client.pk)
        
        return render(request, self.template_name, {
            'form': form,
            'client': client,
        })

@login_required
def payment_instructions(request, pk=None):
    """
    Handle both general and client-specific payment instructions
    """
    client = None
    if pk:
        client = get_object_or_404(Client, pk=pk)
    
    context = {
        'client': client,
        'MPESA_BUSINESS_SHORTCODE': settings.MPESA_BUSINESS_SHORTCODE,
        'COMPANY_CONTACT': settings.COMPANY_CONTACT,
    }
    return render(request, 'billing_app/payment_instructions.html', context)

def payment_receipt(request, pk):
    # Get the payment object
    payment = get_object_or_404(Payment, pk=pk)
    client = payment.client

    # Generate receipt number if it doesn't exist
    if not payment.receipt_number:
        payment.save()  # This will generate the receipt number

    # Create a file-like buffer to receive PDF data
    buffer = BytesIO()

    # Create the PDF object, using the buffer as its "file"
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Set up styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=1,  # Center aligned
        spaceAfter=20
    )
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10
    )
    normal_style = styles['BodyText']

    # Company Header
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width/2, height-50, "PHENOM VENTURES")
    p.setFont("Helvetica", 12)
    p.drawCentredString(width/2, height-70, "Official Payment Receipt")
    p.line(50, height-80, width-50, height-80)

    # Receipt Information
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height-110, "Receipt No:")
    p.setFont("Helvetica", 12)
    p.drawString(150, height-110, payment.receipt_number)

    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height-130, "Date:")
    p.setFont("Helvetica", 12)
    p.drawString(150, height-130, payment.payment_date.strftime("%B %d, %Y"))

    # Client Information
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height-160, "Client Information:")
    p.line(50, height-165, 200, height-165)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, height-180, "Name:")
    p.setFont("Helvetica", 10)
    p.drawString(100, height-180, client.name)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, height-195, "Account:")
    p.setFont("Helvetica", 10)
    p.drawString(100, height-195, client.account_name)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, height-210, "Contact:")
    p.setFont("Helvetica", 10)
    p.drawString(100, height-210, client.contact)

    # Payment Details
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, height-160, "Payment Details:")
    p.line(300, height-165, 450, height-165)

    data = [
        ["Description", "Amount (KES)"],
        ["Package Payment", f"{payment.amount:,.2f}"],
        ["Payment Method", payment.get_payment_method_display()],
        ["Reference", payment.reference],
        ["Processed By", payment.processed_by.get_full_name() or payment.processed_by.username]
    ]

    # Create the table
    table = Table(data, colWidths=[200, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3a7bd5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Draw the table
    table.wrapOn(p, width-100, height)
    table.drawOn(p, 300, height-240)

    # Footer
    p.setFont("Helvetica", 8)
    p.drawCentredString(width/2, 50, "Thank you for your business!")
    p.drawCentredString(width/2, 40, "For any inquiries, contact: billing@phenom-ventures.com")
    p.drawCentredString(width/2, 30, "This is an official receipt from Phenom Ventures")

    # Close the PDF object cleanly
    p.showPage()
    p.save()

    # File response with the PDF
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{payment.receipt_number}.pdf"'
    return response

@login_required
@permission_required('billing_app.send_bulk_sms', raise_exception=True)
def bulk_sms_view(request):
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        
        if not message:
            messages.error(request, "Message cannot be empty")
            return render(request, 'billing_app/dashboard.html', {
                'sms_form_errors': True,
                'total_clients': Client.objects.count(),
                'active_clients': Client.objects.filter(is_active=True).count(),
                # include other dashboard context variables
            })
        
        active_clients = Client.objects.filter(
            is_active=True
        ).exclude(
            Q(phone_number__isnull=True) | Q(phone_number__exact='')
        )
        
        sent_count = 0
        failed_numbers = []
        
        sms = SMSManager()  # Using your existing SMSManager
        
        for client in active_clients:
            try:
                # Use your existing SMSManager to send messages
                sms.send_sms(client.phone_number, message)
                sent_count += 1
                
                # Log the SMS
                SMSLog.objects.create(
                    client=client,
                    message=message,
                    status='DELIVERED',
                    sent_by=request.user
                )
            except Exception as e:
                failed_numbers.append(client.phone_number)
                SMSLog.objects.create(
                    client=client,
                    message=message,
                    status='FAILED',
                    sent_by=request.user,
                    error_message=str(e)
                )
        
        if sent_count > 0:
            messages.success(
                request, 
                f"Successfully sent SMS to {sent_count} clients"
            )
        if failed_numbers:
            messages.warning(
                request,
                f"Failed to send to {len(failed_numbers)} clients: " +
                ", ".join(failed_numbers[:5]) + 
                ("..." if len(failed_numbers) > 5 else "")
            )
        
        return redirect('dashboard')
    
    # For GET requests, show the dashboard with modal
    return redirect('dashboard')

def show_urls(request):
    resolver = get_resolver()
    urls = []
    for url_pattern in resolver.url_patterns:
        urls.append(str(url_pattern.pattern))
    return HttpResponse('<br>'.join(urls))

# ============== Error Handlers ==============
def handler404(request, exception):
    return render(request, '404.html', status=404)

def handler500(request):
    return render(request, '500.html', status=500)