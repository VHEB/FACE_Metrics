"""
Configurações do FACE Metrics.

Pensado pra rodar, na Fase 1, apenas dentro da rede da UniFacens.
Todas as configurações sensíveis vêm de variáveis de ambiente (.env) —
nunca commitar SECRET_KEY, credenciais de banco etc.
"""

from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# decouple.config() procura um arquivo ".env" a partir do diretório onde
# o comando é executado (a raiz do projeto, onde fica o manage.py) e sobe
# nos diretórios pais até achar. Por isso o .env deve ficar ao lado do
# manage.py, não dentro de face_metrics/.
SECRET_KEY = config("DJANGO_SECRET_KEY", default="troque-esta-chave-antes-de-ir-para-producao")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)

# Em produção interna, restrinja aos hosts/IPs da rede da instituição.
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # apps do projeto
    "core",
    "dashboard",
    # de-para pra fase 2 (API): descomentar quando for abrir para o público
    # "rest_framework",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "face_metrics.urls"

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

WSGI_APPLICATION = "face_metrics.wsgi.application"

# Banco de dados: Postgres recomendado (suporta bem os relatórios/consultas
# analíticas que vocês vão precisar depois). Ajuste via variáveis de ambiente.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="face_metrics"),
        "USER": config("DB_USER", default="face_metrics"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Segurança extra para dados sensíveis (LGPD) --------------------------
# Ative estas quando estiver atrás de HTTPS (mesmo interno):
SESSION_COOKIE_SECURE = config("DJANGO_HTTPS", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("DJANGO_HTTPS", default=False, cast=bool)
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Log de auditoria simples via admin (django.contrib.admin já registra
# LogEntry de tudo que é criado/editado/apagado pelo admin).
