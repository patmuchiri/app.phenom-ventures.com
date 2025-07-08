import requests
from django.conf import settings
from .models import SMSLog, Client
import logging

logger = logging.getLogger(__name__)

class SMSManager:
    def __init__(self):
        self.api_key = settings.EASYSENDSMS_API_KEY
        self.sender_id = settings.EASYSENDSMS_SENDER_ID
    
    def send_sms(self, phone_number, message, client=None):
        url = "https://www.easysendsms.com/sms/bulksms-api/bulksms-api"
        
        params = {
            'username': settings.EASYSENDSMS_USERNAME,
            'password': settings.EASYSENDSMS_PASSWORD,
            'from': self.sender_id,
            'to': phone_number,
            'text': message,
            'type': '0',
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Log the SMS
            SMSLog.objects.create(
                client=client,
                message=message,
                status="Sent" if "OK" in response.text else "Failed"
            )
            
            return True
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            SMSLog.objects.create(
                client=client,
                message=message,
                status="Error"
            )
            return False
    
    def send_bulk_sms(self, phone_numbers, message):
        results = []
        for number in phone_numbers:
            results.append(self.send_sms(number, message))
        return all(results)
