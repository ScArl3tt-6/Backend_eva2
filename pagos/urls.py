# ============================================================
# pagos/urls.py — RUTA DE RETORNO DE WEBPAY PLUS
# Responsabilidad: publicar la única URL a la que Transbank redirige
# el navegador del cliente. No está bajo /panel/ (no es parte del
# panel de gestión) ni bajo /api/ (no la llama un cliente de la API,
# la llama el navegador siguiendo el formulario de Transbank).
# ============================================================

from django.urls import path

from . import views_html

urlpatterns_html = [
    path("webpay/retorno/", views_html.retorno_webpay, name="webpay-retorno"),
]
