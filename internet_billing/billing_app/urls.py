from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from .views import (
    home,
    dashboard,
    landing,
    client_toggle_status, 
    client_quick_search,
    manual_payment_processing,     
    ClientDetailView, 
    ClientListView, 
    ClientCreateView, 
    ClientUpdateView,
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserDeleteView,
    PaymentFormView,
    TransactionListView,
    TransactionCreateView,
    TransactionDetailView,
    transaction_receipt_pdf,
    payment_instructions,
    BulkPaymentView,
    bulk_sms_view,
    LoginView,
    UserPasswordChangeView,
    MpesaCallbackView
)

app_name = 'billing_app'

urlpatterns = [
    # Authentication URLs
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Core URLs
    path('', views.home, name='home'),  # Using the existing home function view
    path('dashboard/', views.dashboard, name='dashboard'),  # Using the existing dashboard function
    path('landing/', views.landing, name='landing'),
    
    # User Management URLs
    path('users/', UserListView.as_view(), name='user_list'),
    path('users/add/', UserCreateView.as_view(), name='add_user'),
    path('users/<int:pk>/edit/', UserUpdateView.as_view(), name='edit_user'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='delete_user'),
    path('users/<int:pk>/change-password/', UserPasswordChangeView.as_view(), name='change_password'),
    
    # Client Management URLs
    path('clients/', ClientListView.as_view(), name='client_list'),
    path('clients/create/', ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/update/', ClientUpdateView.as_view(), name='client_update'),
    path('clients/<int:pk>/toggle-status/', views.client_toggle_status, name='client_toggle_status'),
    path('clients/quick-search/', views.client_quick_search, name='client_quick_search'),
    path('clients/<int:pk>/send-email/', views.send_client_email, name='send_client_email'),
    path('clients/<int:pk>/send-sms/', views.send_client_sms, name='send_client_sms'),
    path('clients/<int:pk>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),
    
    # Payment URLs
    path('payments/form/', PaymentFormView.as_view(), name='payment_form'),
    path('payments/form/<int:client_pk>/', PaymentFormView.as_view(), name='client_payment_form'),
    path('payments/<int:pk>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('payment-instructions/', views.payment_instructions, name='payment_instructions'),
    path('clients/<int:pk>/payment-instructions/', views.payment_instructions, name='client_payment_instructions'),
    
    # Transaction URLs
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('transactions/create/', TransactionCreateView.as_view(), name='transaction_create'),
    path('transactions/bulk/', BulkPaymentView.as_view(), name='bulk_payment'),
    path('transactions/<int:pk>/', TransactionDetailView.as_view(), name='transaction_detail'),
    path('transactions/<int:pk>/receipt/', transaction_receipt_pdf, name='transaction_receipt'),
    
    # Password Change URLs
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
    
    # Other URLs
    path('bulk-sms/', bulk_sms_view, name='bulk_sms'),
    path('mpesa/callback/', MpesaCallbackView.as_view(), name='mpesa_callback'),
    path('reports/financial/', views.financial_reports, name='financial_reports'),
    path('show-urls/', views.show_urls, name='show_urls'),
]