from pathlib import Path
import os
from dotenv import load_dotenv
from django.contrib.messages import constants as messages
from django.core.exceptions import ImproperlyConfigured

# Charger le fichier .env
load_dotenv()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# ══════════════════════════════════════════
# SÉCURITÉ
# ══════════════════════════════════════════
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-key-do-not-use-in-production'
    else:
        raise ImproperlyConfigured(
            "La variable d'environnement SECRET_KEY est obligatoire en production."
        )


def _env_list(name, default=''):
    """Lit une variable d'environnement 'a,b,c' et renvoie une liste propre."""
    return [v.strip() for v in os.environ.get(name, default).split(',') if v.strip()]


# Domaine public (serveur web) + accès locaux (healthchecks, tests)
SITE_DOMAIN = os.environ.get('SITE_DOMAIN', 'bwanafacturation.bwhub.tech')
ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', f'{SITE_DOMAIN},127.0.0.1,localhost')

# Redirections HTTPS – seulement en production
if DEBUG:
    SECURE_SSL_REDIRECT = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
else:
    SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 31536000))

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ══════════════════════════════════════════
# APPLICATIONS
# ══════════════════════════════════════════
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users',
    'clients',
    'devis',
    'factures',
    'taxes',
    'produits',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'users.admin_middleware.MaintenanceMiddleware',
]

ROOT_URLCONF = 'config.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ══════════════════════════════════════════
# BASE DE DONNÉES
# ══════════════════════════════════════════
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.environ.get('DB_NAME', 'gestion_df'),
        'USER':     os.environ.get('DB_USER', 'admis_pdf'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'root'),
        'HOST':     os.environ.get('DB_HOST', 'localhost'),
        'PORT':     os.environ.get('DB_PORT', '5432'),
    }
}

# Développement local sans PostgreSQL : USE_SQLITE=True dans le .env
if os.environ.get('USE_SQLITE', 'False') == 'True':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME':   BASE_DIR / 'db.sqlite3',
    }

# ══════════════════════════════════════════
# MOT DE PASSE
# ══════════════════════════════════════════
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ══════════════════════════════════════════
# INTERNATIONALISATION
# ══════════════════════════════════════════
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Ouagadougou'
USE_I18N = True
USE_TZ = True

# ══════════════════════════════════════════
# FICHIERS STATIQUES & MEDIA
# ══════════════════════════════════════════
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ══════════════════════════════════════════
# AUTHENTIFICATION
# ══════════════════════════════════════════
LOGIN_URL = '/BwanaFacturation/users/connexion/'
LOGIN_REDIRECT_URL = '/BwanaFacturation/devis/tableau-de-bord/'
LOGOUT_REDIRECT_URL = '/BwanaFacturation/users/connexion/'

# ══════════════════════════════════════════
# SESSIONS
# ══════════════════════════════════════════
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# ══════════════════════════════════════════
# MESSAGES BOOTSTRAP
# ══════════════════════════════════════════
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# ══════════════════════════════════════════
# EMAIL PRINCIPAL (notifications, validation...)
# ══════════════════════════════════════════
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_HOST_USER', 'noreply@bwanafacturation.com')

# ══════════════════════════════════════════
# EMAIL DÉDIÉ AUX FACTURES ET DEVIS (2ème compte)
# ══════════════════════════════════════════
FACTURE_EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# Sans compte dédié (FACTURE_*), on utilise le compte principal ci-dessus.
FACTURE_EMAIL_HOST = os.environ.get('FACTURE_EMAIL_HOST', EMAIL_HOST)
FACTURE_EMAIL_PORT = int(os.environ.get('FACTURE_EMAIL_PORT', EMAIL_PORT))
FACTURE_EMAIL_USE_TLS = True
FACTURE_EMAIL_HOST_USER = os.environ.get('FACTURE_EMAIL_HOST_USER') or EMAIL_HOST_USER
FACTURE_EMAIL_HOST_PASSWORD = os.environ.get('FACTURE_EMAIL_HOST_PASSWORD') or EMAIL_HOST_PASSWORD
FACTURE_DEFAULT_FROM_EMAIL = (os.environ.get('FACTURE_DEFAULT_FROM_EMAIL')
                              or FACTURE_EMAIL_HOST_USER
                              or 'factures@bwanafacturation.com')

# ══════════════════════════════════════════
# CSRF & SÉCURITÉ
# ══════════════════════════════════════════
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS', f'https://{SITE_DOMAIN}')

if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        'http://127.0.0.1:8000',
        'http://localhost:8000',
    ]

# ══════════════════════════════════════════
# SITE
# ══════════════════════════════════════════
SITE_URL = os.environ.get('SITE_URL', f'https://{SITE_DOMAIN}')
