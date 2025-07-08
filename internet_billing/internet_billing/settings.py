"""
Django settings for internet_billing project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
SECRET_KEY = 'django-insecure-j(c5cj($+_jyrtuwfv=+-whx4$pzkuii%3ipu*cii8d-v#&j1m'
DEBUG = True
ALLOWED_HOSTS = []

# ================== Application definition ==================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'crispy_forms',
    'crispy_bootstrap4',
    'widget_tweaks',
    'bootstrap4',
    'billing_app.apps.BillingAppConfig',  # Changed to use app config
]

CRISPY_TEMPLATE_PACK = "bootstrap4"

# Custom User Model (MUST come before auth middleware)
AUTH_USER_MODEL = 'billing_app.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'internet_billing.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Custom context processors
                'billing_app.context_processors.company_info',
            ],
            'builtins': [
                'django.contrib.humanize.templatetags.humanize',
            ],
        },
    },
]

WSGI_APPLICATION = 'internet_billing.wsgi.application'

# ================== Database ==================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ================== Password validation ==================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ================== Internationalization ==================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ================== Static files ==================
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# ================== Media files ==================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ================== Default primary key ==================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ================== Authentication ==================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = 'home'

# ================== Session Settings ==================
SESSION_COOKIE_AGE = 86400  # 1 day in seconds
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_NAME = 'ispsys_sessionid'

# ================== Custom Settings ==================

# Company Information
COMPANY_NAME = "PHENOM VENTURES LTD"
COMPANY_CONTACT = "0702473609"
COMPANY_EMAIL = "info@phenom-ventures.com"
COMPANY_ADDRESS = "Nairobi, Kenya"
WORKING_HOURS = "8:00 AM - 5:00 PM, Monday to Friday"

# MikroTik RouterOS API Settings
MIKROTIK_HOST = '102.0.17.148'  # Your router IP
MIKROTIK_USERNAME = 'admin'      # API username
MIKROTIK_PASSWORD = '#@pheth2043'   # API password
MIKROTIK_PORT = 8728             # API port

# MPESA Settings
MPESA_CONSUMER_KEY = 'your_consumer_key'
MPESA_CONSUMER_SECRET = 'your_consumer_secret'
MPESA_BUSINESS_SHORTCODE = '802007'
MPESA_PASSKEY = 'your_passkey'
MPESA_CALLBACK_URL = 'https://yourdomain.com/mpesa-callback/'
MPESA_TRANSACTION_TYPE = 'CustomerPayBillOnline'

# SMS Settings
SMS_PROVIDER = 'easysendsms'  # or 'africastalking', 'twilio'
SMS_API_KEY = 'your_api_key'
SMS_USERNAME = 'your_username'
SMS_PASSWORD = 'your_password'
SMS_SENDER_ID = 'PHENOM'

# Bank Payment Details (optional)
BANK_NAME = "EQUITY BANK"
BANK_ACCOUNT_NAME = "PHENOM VENTURES LIMITED"
BANK_ACCOUNT_NUMBER = "0110261790114"
BANK_BRANCH = "Nyeri Branch"

# Email Settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.your-email-provider.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your@email.com'
EMAIL_HOST_PASSWORD = 'your-email-password'
DEFAULT_FROM_EMAIL = 'noreply@phenom-ventures.com'
SERVER_EMAIL = 'server@phenom-ventures.com'

# ================== Security Settings ==================
if not DEBUG:
    # HTTPS Settings
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    
    # HSTS Settings
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Other security settings
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

# ================== Logging ==================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'debug.log'),
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'billing_app': {
            'handlers': ['file'],
            'level': 'DEBUG',
        },
    },
}

# ================== Custom Constants ==================
INVOICE_PREFIX = 'INV'
RECEIPT_PREFIX = 'RCP'
