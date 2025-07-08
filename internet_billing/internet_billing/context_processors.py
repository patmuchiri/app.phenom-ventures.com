from django.conf import settings

def company_info(request):
    return {
        'company_name': settings.COMPANY_NAME,
        'company_contact': settings.COMPANY_CONTACT,
        'company_email': settings.COMPANY_EMAIL,
    }
