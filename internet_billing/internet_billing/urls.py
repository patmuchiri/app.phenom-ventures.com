from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy
from billing_app.views import (
    home,  # Using the existing function view
    dashboard,  # Using the existing function view
    landing,  # Using the existing function view
    handler404, 
    handler500,
    client_toggle_status, 
    client_quick_search,
    manual_payment_processing, 
    MpesaCallbackView,
    ClientListView, 
    ClientCreateView,
    ClientDetailView,
    ClientUpdateView,
    ClientDeleteView,
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserDeleteView,
    TransactionListView,
    TransactionCreateView,
    TransactionDetailView,
    bulk_sms_view,
    BulkPaymentView,
    LoginView,
    financial_reports,
    payment_instructions,
    payment_receipt,
    transaction_receipt_pdf,
    UserPasswordChangeView
)

urlpatterns = [
    # Admin URL
    path('admin/', admin.site.urls),
    
    # Authentication URLs
    path('accounts/login/', LoginView.as_view(), name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    
    # Core Application URLs
    path('', home, name='home'),  # Using function view
    path('dashboard/', dashboard, name='dashboard'),  # Using function view
    path('landing/', landing, name='landing'),  # Using function view
    path('', include('billing_app.urls')),
    
    # Client Management URLs
    path('clients/', ClientListView.as_view(), name='client_list'),
    path('clients/new/', ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/edit/', ClientUpdateView.as_view(), name='client_update'),
    path('clients/<int:pk>/delete/', ClientDeleteView.as_view(), name='client_delete'),
    path('clients/<int:pk>/toggle-status/', client_toggle_status, name='client_toggle_status'),
    path('clients/quick-search/', client_quick_search, name='client_quick_search'),
    path('clients/<int:pk>/payment-instructions/', payment_instructions, name='client_payment_instructions'),
    
    # Transaction Management URLs
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('transactions/new/', TransactionCreateView.as_view(), name='transaction_create'),
    path('transactions/bulk/', BulkPaymentView.as_view(), name='bulk_payment'),
    path('transactions/<int:pk>/', TransactionDetailView.as_view(), name='transaction_detail'),
    path('transactions/<int:pk>/receipt/', transaction_receipt_pdf, name='transaction_receipt'),
    
    # User Management URLs
    path('users/', UserListView.as_view(), name='user_list'),
    path('users/create/', UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/change-password/', UserPasswordChangeView.as_view(), name='change_password'),
    
    # Payment Processing URLs
    path('payments/manual/', manual_payment_processing, name='manual_payment'),
    path('payments/manual/<int:client_pk>/', manual_payment_processing, name='manual_payment_client'),
    path('payments/<int:pk>/receipt/', payment_receipt, name='payment_receipt'),
    path('payment-instructions/', payment_instructions, name='payment_instructions'),
    path('mpesa-callback/', MpesaCallbackView.as_view(), name='mpesa_callback'),
    
    # Reporting URLs
    path('reports/financial/', financial_reports, name='financial_reports'),
    
    # Bulk SMS URL
    path('bulk-sms/', bulk_sms_view, name='bulk_sms'),
    
    # Password change URLs (using Django's built-in views)
    path('password-change/', 
         auth_views.PasswordChangeView.as_view(
             template_name='billing_app/change_password.html',
             success_url=reverse_lazy('billing_app:user_list')
         ),
         name='password_change'),
    path('password-change/done/', 
         auth_views.PasswordChangeDoneView.as_view(
             template_name='billing_app/change_password_done.html'
         ),
         name='password_change_done'),
]

# Add error handlers
handler404 = 'billing_app.views.handler404'
handler500 = 'billing_app.views.handler500'