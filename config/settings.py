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
# HELPERS (lecture des variables d'environnement)
# ══════════════════════════════════════════
_TRUE_VALUES = {'1', 'true', 'yes', 'on', 'y', 't'}


def _env(name, default=''):
    """Texte : renvoie la valeur nettoyée, ou `default` si absente / vide."""
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return default
    return value.strip()


def _env_bool(name, default=False):
    """Booléen : 1/true/yes/on (insensible à la casse) => True."""
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return default
    return value.strip().lower() in _TRUE_VALUES


def _env_int(name, default=0):
    """Entier : lève une erreur claire si la valeur n'est pas un nombre."""
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return default
    try:
        return int(value.strip())
    except ValueError:
        raise ImproperlyConfigured(
            f"La variable d'environnement {name} doit être un nombre entier (reçu : {value!r})."
        )


def _env_list(name, default=''):
    """Liste : lit une variable 'a,b,c' et renvoie une liste propre."""
    return [v.strip() for v in os.environ.get(name, default).split(',') if v.strip()]


# ══════════════════════════════════════════
# SÉCURITÉ
# ══════════════════════════════════════════
DEBUG = _env_bool('DEBUG', False)

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-key-do-not-use-in-production'
    else:
        raise ImproperlyConfigured(
            "La variable d'environnement SECRET_KEY est obligatoire en production."
        )

# Domaine public (serveur web) + accès locaux (healthchecks, tests)
SITE_DOMAIN = _env('SITE_DOMAIN', 'bwanafacturation.bwhub.tech')
ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', f'{SITE_DOMAIN},127.0.0.1,localhost')

# Redirections HTTPS / cookies sécurisés : actifs en production, désactivés en DEBUG
# (chacun peut être forcé via .env)
SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = _env_int('SECURE_HSTS_SECONDS', 0 if DEBUG else 31536000)

# Derrière un reverse proxy (Nginx, etc.) qui envoie X-Forwarded-Proto
if _env_bool('USE_PROXY_SSL_HEADER', True):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

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
        'ENGINE':   _env('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME':     _env('DB_NAME', 'gestion_df'),
        'USER':     _env('DB_USER', 'admis_pdf'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST':     _env('DB_HOST', 'localhost'),
        'PORT':     _env('DB_PORT', '5432'),
    }
}

# Développement local sans PostgreSQL : USE_SQLITE=True dans le .env
if _env_bool('USE_SQLITE', False):
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME':   BASE_DIR / _env('SQLITE_NAME', 'db.sqlite3'),
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
LANGUAGE_CODE = _env('LANGUAGE_CODE', 'fr-fr')
TIME_ZONE = _env('TIME_ZONE', 'Africa/Ouagadougou')
USE_I18N = _env_bool('USE_I18N', True)
USE_TZ = _env_bool('USE_TZ', True)

# ══════════════════════════════════════════
# FICHIERS STATIQUES & MEDIA
# ══════════════════════════════════════════
STATIC_URL = _env('STATIC_URL', '/static/')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = _env('STATIC_ROOT', os.path.join(BASE_DIR, 'staticfiles'))

MEDIA_URL = _env('MEDIA_URL', '/media/')
MEDIA_ROOT = _env('MEDIA_ROOT', os.path.join(BASE_DIR, 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ══════════════════════════════════════════
# AUTHENTIFICATION
# ══════════════════════════════════════════
# Préfixe d'URL de l'application (doit correspondre à config/urls.py)
APP_URL_PREFIX = _env('APP_URL_PREFIX', '/BwanaFacturation').rstrip('/')

LOGIN_URL = _env('LOGIN_URL', f'{APP_URL_PREFIX}/users/connexion/')
LOGIN_REDIRECT_URL = _env('LOGIN_REDIRECT_URL', f'{APP_URL_PREFIX}/devis/tableau-de-bord/')
LOGOUT_REDIRECT_URL = _env('LOGOUT_REDIRECT_URL', f'{APP_URL_PREFIX}/users/connexion/')

# ══════════════════════════════════════════
# SESSIONS
# ══════════════════════════════════════════
SESSION_COOKIE_AGE = _env_int('SESSION_COOKIE_AGE', 3600)
SESSION_EXPIRE_AT_BROWSER_CLOSE = _env_bool('SESSION_EXPIRE_AT_BROWSER_CLOSE', True)
SESSION_SAVE_EVERY_REQUEST = _env_bool('SESSION_SAVE_EVERY_REQUEST', True)
SESSION_COOKIE_HTTPONLY = _env_bool('SESSION_COOKIE_HTTPONLY', True)
SESSION_COOKIE_SAMESITE = _env('SESSION_COOKIE_SAMESITE', 'Lax')

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
# EMAIL PRINCIPAL (activation, réinitialisation, notifications...)
# ══════════════════════════════════════════
# Par défaut : SMTP Hostinger. Le chiffrement se déduit du port :
#   465 => SSL implicite | 587 => STARTTLS (TLS)
# Chaque valeur peut être forcée dans le .env.
EMAIL_BACKEND = _env('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = _env('EMAIL_HOST', 'smtp.hostinger.com')
EMAIL_PORT = _env_int('EMAIL_PORT', 465)
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', EMAIL_PORT == 465)
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', EMAIL_PORT == 587)
EMAIL_TIMEOUT = _env_int('EMAIL_TIMEOUT', 30)
EMAIL_HOST_USER = _env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = _env('DEFAULT_FROM_EMAIL', '') or EMAIL_HOST_USER or f'noreply@{SITE_DOMAIN}'

# ══════════════════════════════════════════
# EMAIL DÉDIÉ AUX FACTURES ET DEVIS (2ème compte)
# ══════════════════════════════════════════
# Sans variables FACTURE_*, on réutilise le compte principal ci-dessus.
# NB : si une configuration « factures » active existe dans
# Administration → Configuration email, elle est prioritaire sur ce bloc.
FACTURE_EMAIL_BACKEND = _env('FACTURE_EMAIL_BACKEND', EMAIL_BACKEND)
FACTURE_EMAIL_HOST = _env('FACTURE_EMAIL_HOST', EMAIL_HOST)
FACTURE_EMAIL_PORT = _env_int('FACTURE_EMAIL_PORT', EMAIL_PORT)
FACTURE_EMAIL_USE_SSL = _env_bool('FACTURE_EMAIL_USE_SSL', FACTURE_EMAIL_PORT == 465)
FACTURE_EMAIL_USE_TLS = _env_bool('FACTURE_EMAIL_USE_TLS', FACTURE_EMAIL_PORT == 587)
FACTURE_EMAIL_HOST_USER = _env('FACTURE_EMAIL_HOST_USER', '') or EMAIL_HOST_USER
FACTURE_EMAIL_HOST_PASSWORD = os.environ.get('FACTURE_EMAIL_HOST_PASSWORD') or EMAIL_HOST_PASSWORD
FACTURE_DEFAULT_FROM_EMAIL = (
    _env('FACTURE_DEFAULT_FROM_EMAIL', '')
    or FACTURE_EMAIL_HOST_USER
    or f'factures@{SITE_DOMAIN}'
)

# Garde-fou : SSL et TLS sont mutuellement exclusifs (sinon Django plante à l'envoi)
if EMAIL_USE_SSL and EMAIL_USE_TLS:
    raise ImproperlyConfigured(
        "EMAIL_USE_SSL et EMAIL_USE_TLS ne peuvent pas être actifs en même temps "
        "(465 => SSL, 587 => TLS)."
    )
if FACTURE_EMAIL_USE_SSL and FACTURE_EMAIL_USE_TLS:
    raise ImproperlyConfigured(
        "FACTURE_EMAIL_USE_SSL et FACTURE_EMAIL_USE_TLS ne peuvent pas être actifs "
        "en même temps (465 => SSL, 587 => TLS)."
    )

# ══════════════════════════════════════════
# INSCRIPTION
# ══════════════════════════════════════════
# False (recommandé) : un compte reste inactif tant que l'email d'activation n'est pas confirmé,
# même si l'envoi de l'email échoue. True : active et connecte directement le compte si l'envoi échoue.
ALLOW_SIGNUP_WITHOUT_EMAIL = _env_bool('ALLOW_SIGNUP_WITHOUT_EMAIL', False)

# ══════════════════════════════════════════
# LOGS (visibles dans la sortie de gunicorn / journalctl)
# ══════════════════════════════════════════
LOG_LEVEL = _env('LOG_LEVEL', 'INFO').upper()
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '%(asctime)s [%(levelname)s] %(name)s : %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'root': {'handlers': ['console'], 'level': LOG_LEVEL},
}

# ══════════════════════════════════════════
# CSRF & SÉCURITÉ
# ══════════════════════════════════════════
CSRF_COOKIE_HTTPONLY = _env_bool('CSRF_COOKIE_HTTPONLY', False)
CSRF_COOKIE_SAMESITE = _env('CSRF_COOKIE_SAMESITE', 'Lax')
CSRF_USE_SESSIONS = _env_bool('CSRF_USE_SESSIONS', False)
CSRF_COOKIE_NAME = _env('CSRF_COOKIE_NAME', 'csrftoken')
CSRF_HEADER_NAME = _env('CSRF_HEADER_NAME', 'HTTP_X_CSRFTOKEN')

SECURE_BROWSER_XSS_FILTER = _env_bool('SECURE_BROWSER_XSS_FILTER', True)
SECURE_CONTENT_TYPE_NOSNIFF = _env_bool('SECURE_CONTENT_TYPE_NOSNIFF', True)
X_FRAME_OPTIONS = _env('X_FRAME_OPTIONS', 'DENY')

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
SITE_URL = _env('SITE_URL', f'https://{SITE_DOMAIN}')
