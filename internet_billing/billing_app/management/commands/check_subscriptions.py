# billing_app/management/commands/check_subscriptions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import Client, ClientSubscription, Payment
from ...mikrotik import MikrotikManager
from ...sms import SMSManager
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Checks client subscriptions and deactivates expired ones'
    
    def handle(self, *args, **options):
        today = timezone.now().date()
        expired_clients = ClientSubscription.objects.filter(end_date__lt=today, client__is_active=True)
        
        mikrotik = MikrotikManager(settings.DEFAULT_ROUTER_ID)
        sms = SMSManager()
        
        for subscription in expired_clients:
            client = subscription.client
            
            # Check for payments that might cover the period
            latest_payment = Payment.objects.filter(client=client).order_by('-payment_date').first()
            
            if not latest_payment or latest_payment.status != 'completed':
                # Deactivate client
                success = mikrotik.deactivate_client(client.ip_address)
                
                if success:
                    client.is_active = False
                    client.save()
                    
                    # Send deactivation SMS
                    sms.send_sms(
                        client.contact,
                        f"Dear {client.name}, your internet subscription has expired. Please renew to continue enjoying our services."
                    )
                    
                    self.stdout.write(f"Deactivated client: {client.name}")
                else:
                    logger.error(f"Failed to deactivate client: {client.name}")
        
        mikrotik.close_connection()
        self.stdout.write("Subscription check completed")
