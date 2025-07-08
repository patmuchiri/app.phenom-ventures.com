from django.apps import AppConfig

class BillingAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing_app'
    
    def ready(self):
        pass  # Remove the signals import for now
