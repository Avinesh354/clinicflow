import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_SECRET = "dev-only-change-me"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEV_SECRET)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"  # development default; set DJANGO_DEBUG=0 in production
if not DEBUG and SECRET_KEY == DEV_SECRET:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0.")
# Any host in development; in production list your domain(s), e.g. DJANGO_ALLOWED_HOSTS=clinic.example.com
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework",
    "clinic",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves the React build and Django admin assets
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.mysql",
    "NAME": os.environ.get("DB_NAME", "clinicflow"),
    "USER": os.environ.get("DB_USER", "clinicflow"),
    "PASSWORD": os.environ.get("DB_PASSWORD", "clinicflow"),
    "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
    "PORT": os.environ.get("DB_PORT", "3306"),
    "OPTIONS": {
        "charset": "utf8mb4",
        # READ COMMITTED: after taking a row lock, reads see the previous holder's commit.
        "isolation_level": "read committed",
    },
}}

# Store UTC, group/display in clinic-local time (matters for peak-hour analytics).
USE_TZ = True
TIME_ZONE = os.environ.get("CLINIC_TZ", "Asia/Kolkata")
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # `collectstatic` target (admin CSS/JS)

# One site: Django also serves the built React app. `npm run build` (in frontend/) writes it to backend/spa.
SPA_DIR = BASE_DIR / "spa"
if SPA_DIR.is_dir():
    WHITENOISE_ROOT = SPA_DIR
    WHITENOISE_INDEX_FILE = True  # "/" -> index.html

# Public demo site: opening today's appointments auto-creates a schedule if there is none (see clinic/demo.py).
DEMO_MODE = os.environ.get("DEMO_MODE", "0") == "1"

# Cookies are only sent over HTTPS in production (set DJANGO_SECURE_COOKIES=0 to test over plain http).
SECURE_COOKIES = os.environ.get("DJANGO_SECURE_COOKIES", "0" if DEBUG else "1") == "1"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_COOKIES
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

# Booking grid: every appointment occupies whole slots, aligned in clinic-local time.
CLINIC_SLOT_MINUTES = int(os.environ.get("CLINIC_SLOT_MINUTES", "20"))
CLINIC_MAX_APPOINTMENT_MINUTES = int(os.environ.get("CLINIC_MAX_APPOINTMENT_MINUTES", "120"))

# The Vite dev server (frontend) talks to Django through a proxy; trust its origin for CSRF.
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
