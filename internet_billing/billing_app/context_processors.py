from django.conf import settings

def company_info(request):
    """Adds company information to every template context"""
    return {
        'COMPANY_NAME': settings.COMPANY_NAME,
        'COMPANY_CONTACT': settings.COMPANY_CONTACT,
        'COMPANY_EMAIL': settings.COMPANY_EMAIL,
        'COMPANY_ADDRESS': settings.COMPANY_ADDRESS,
    }
