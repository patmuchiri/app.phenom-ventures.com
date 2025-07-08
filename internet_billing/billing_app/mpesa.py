import requests
import base64
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from io import BytesIO
from reportlab.pdfgen import canvas
import logging
from .models import Payment, Client, ClientSubscription, SMSLog
from .mikrotik import MikrotikManager
from .sms import SMSManager

logger = logging.getLogger(__name__)

class MpesaGateway:
    def __init__(self):
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.business_shortcode = settings.MPESA_BUSINESS_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self):
        """Get or refresh the OAuth access token"""
        if self.access_token and self.token_expiry and self.token_expiry > datetime.now():
            return self.access_token
        
        url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        auth = base64.b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode()).decode()
        
        headers = {'Authorization': f'Basic {auth}'}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            self.access_token = data['access_token']
            self.token_expiry = datetime.now() + timedelta(seconds=data['expires_in'] - 60)
            return self.access_token
        except Exception as e:
            logger.error(f"Error getting MPESA access token: {e}")
            raise
    
    def process_payment_callback(self, callback_data):
        """Process MPESA STK push callback data"""
        try:
            result_code = callback_data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
            if result_code == 0:
                callback = callback_data['Body']['stkCallback']
                metadata = callback['CallbackMetadata']['Item']
                
                payment_data = {
                    'amount': next(item['Value'] for item in metadata if item['Name'] == 'Amount'),
                    'mpesa_code': next(item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'),
                    'phone': next(item['Value'] for item in metadata if item['Name'] == 'PhoneNumber'),
                    'account_name': next((item['Value'] for item in metadata if item['Name'] == 'AccountReference'), None),
                }
                
                if not payment_data['account_name']:
                    logger.error("No account name provided in MPESA payment")
                    self.log_failed_payment(payment_data, "Missing account name")
                    return False
                
                try:
                    client = Client.objects.get(account_name__iexact=payment_data['account_name'])
                    return self.process_successful_payment(client, payment_data)
                
                except Client.DoesNotExist:
                    error_msg = f"No client found with account name {payment_data['account_name']}"
                    logger.error(error_msg)
                    self.log_failed_payment(payment_data, error_msg)
                    return False
                
                except Client.MultipleObjectsReturned:
                    error_msg = f"Multiple clients found with account name {payment_data['account_name']}"
                    logger.error(error_msg)
                    self.log_failed_payment(payment_data, error_msg)
                    return False
            
            else:
                error_msg = f"Payment failed: {callback_data}"
                logger.error(error_msg)
                self.log_failed_payment(payment_data, error_msg)
                return False
        
        except Exception as e:
            error_msg = f"Error processing MPESA callback: {e}"
            logger.error(error_msg)
            if 'payment_data' in locals():
                self.log_failed_payment(payment_data, error_msg)
            return False
    
    def process_successful_payment(self, client, payment_data):
        """Handle successful payment processing"""
        payment = Payment.objects.create(
            client=client,
            amount=payment_data['amount'],
            mpesa_code=payment_data['mpesa_code'],
            status='completed'
        )
        
        if self.activate_client(client, payment):
            logger.info(f"Successfully processed payment for client {client.account_name}")
            return True
        
        payment.status = 'pending'
        payment.save()
        logger.error(f"Payment recorded but client activation failed for {client.account_name}")
        return False
    
    def log_failed_payment(self, payment_data, reason):
        """Record failed payment attempts"""
        if payment_data.get('mpesa_code'):
            Payment.objects.create(
                mpesa_code=payment_data['mpesa_code'],
                amount=payment_data.get('amount', 0),
                status='failed',
                notes=reason
            )
    
    def activate_client(self, client, payment):
        """Activate client service after payment"""
        try:
            subscription = ClientSubscription.objects.filter(
                client=client,
                is_active=True
            ).latest('start_date')
            
            mikrotik = MikrotikManager(settings.DEFAULT_ROUTER_ID)
            success = mikrotik.update_client_bandwidth(
                client.ip_address,
                f"{subscription.package.speed_mbps}M",
                f"{subscription.package.speed_mbps}M"
            )
            mikrotik.close_connection()
            
            if success:
                client.is_active = True
                client.save()
                self.send_notifications(client, payment, subscription)
                return True
            
            return False
        
        except ClientSubscription.DoesNotExist:
            logger.error(f"No active subscription found for client {client.account_name}")
            return False
        
        except Exception as e:
            logger.error(f"Error activating client {client.account_name}: {e}")
            return False
    
    def send_notifications(self, client, payment, subscription):
        """Send all activation notifications"""
        self.send_activation_sms(client, payment, subscription)
        self.send_receipt_email(client, payment)
    
    def send_activation_sms(self, client, payment, subscription):
        """Send activation SMS to client"""
        try:
            message = (
                f"Dear {client.name}, your {subscription.package.name} package "
                f"has been activated. {subscription.package.speed_mbps}Mbps, "
                f"KSh{payment.amount} paid. Receipt: {payment.mpesa_code}. "
                f"Expires: {subscription.end_date.strftime('%d/%m/%Y')}"
            )
            
            sms = SMSManager()
            sms.send_sms(client.contact, message)
            
            # Log the SMS
            SMSLog.objects.create(
                client=client,
                message=message,
                status="Sent",
                sms_type="activation",
                recipient_number=client.contact
            )
        
        except Exception as e:
            logger.error(f"Failed to send activation SMS to {client.contact}: {e}")
    
    def send_receipt_email(self, client, payment):
        """Send payment receipt email with PDF attachment"""
        try:
            # Generate PDF receipt
            pdf_content = self.generate_receipt_pdf(client, payment)
            
            # Prepare email
            subject = f"Payment Receipt - KSh{payment.amount}"
            body = (
                f"Dear {client.name},\n\n"
                f"Your payment receipt for KSh{payment.amount} is attached.\n"
                f"Transaction ID: {payment.mpesa_code}\n\n"
                f"Thank you for your business!\n\n"
                f"Sincerely,\n"
                f"{settings.COMPANY_NAME}\n"
                f"{settings.COMPANY_CONTACT}"
            )
            
            email = EmailMessage(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [client.email],
                reply_to=[settings.COMPANY_EMAIL]
            )
            email.attach(
                f"receipt_{payment.mpesa_code}.pdf",
                pdf_content,
                'application/pdf'
            )
            email.send()
            
        except Exception as e:
            logger.error(f"Failed to send receipt email to {client.email}: {e}")
    
    def generate_receipt_pdf(self, client, payment):
        """Generate PDF receipt content"""
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        
        # Header
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 800, settings.COMPANY_NAME)
        p.setFont("Helvetica", 12)
        p.drawString(100, 780, "OFFICIAL PAYMENT RECEIPT")
        
        # Receipt details
        p.setFont("Helvetica", 10)
        p.drawString(100, 750, f"Date: {payment.payment_date.strftime('%Y-%m-%d %H:%M')}")
        p.drawString(100, 730, f"Receipt No: {payment.mpesa_code}")
        p.drawString(100, 710, f"Client: {client.name}")
        p.drawString(100, 690, f"Account: {client.account_name}")
        p.drawString(100, 670, f"Amount: KSh{payment.amount:,.2f}")
        
        # Footer
        p.drawString(100, 640, "Thank you for your business!")
        p.drawString(100, 620, f"For inquiries, contact: {settings.COMPANY_CONTACT}")
        
        p.showPage()
        p.save()
        
        pdf = buffer.getvalue()
        buffer.close()
        return pdf
    
    def initiate_stk_push(self, phone_number, amount, account_reference, description):
        """Initiate STK push payment request"""
        try:
            access_token = self.get_access_token()
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.business_shortcode}{self.passkey}{timestamp}".encode()
            ).decode()
            
            payload = {
                "BusinessShortCode": self.business_shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": amount,
                "PartyA": phone_number,
                "PartyB": self.business_shortcode,
                "PhoneNumber": phone_number,
                "CallBackURL": self.callback_url,
                "AccountReference": account_reference,
                "TransactionDesc": description
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            return response.json()
        
        except Exception as e:
            logger.error(f"Error initiating STK push: {e}")
            raise
