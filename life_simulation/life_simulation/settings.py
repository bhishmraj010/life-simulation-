from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(BASE_DIR / ".env")

# ==========================
# Security
# ==========================

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-life-simulation-change-this-in-production-xyz123"
)

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "life-simulation-9bqz.onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://life-simulation-9bqz.onrender.com",
]

# ==========================
# Applications
# ==========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "users",
    "tasks",
    "tracker",
    "reports",
    "diet",
]

# ==========================
# Middleware
# ==========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "life_simulation.urls"

# ==========================
# Templates
# ==========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "life_simulation.wsgi.application"

# ==========================
# Database
# ==========================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ==========================
# User Model
# ==========================

AUTH_USER_MODEL = "users.CustomUser"

# ==========================
# Authentication
# ==========================

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/users/login/"

# ==========================
# Password Validators
# ==========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]

# ==========================
# Localization
# ==========================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True

# ==========================
# Static Files
# ==========================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# ==========================
# Media Files
# ==========================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==========================
# Email
# ==========================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ==========================
# Default PK
# ==========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"