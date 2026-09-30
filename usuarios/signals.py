# ============================================================
# usuarios/signals.py — SEÑALES DEL CICLO DE VIDA DEL USUARIO
# Responsabilidad: garantizar que todo cliente tenga su carro de
# compras persistente desde el instante en que se crea la cuenta.
#
# Por qué con una señal y no en la vista de registro: el usuario
# se puede crear desde la API, desde el panel HTML, desde el
# comando seed_data, desde createsuperuser o desde el admin de
# Django. La señal es el único punto por el que pasan todos esos
# caminos, así que es imposible terminar con un cliente sin carro.
# ============================================================

from django.db.models.signals import post_save
from django.dispatch import receiver

from carro.models import Carro

from .models import Rol, Usuario


# ============================================================
# BLOQUE 1 — CREACIÓN AUTOMÁTICA DEL CARRO
# Se dispara después de guardar un Usuario. Usa get_or_create
# para ser idempotente: si el carro ya existe no lo duplica, lo
# que además respeta la relación 1 a 1 del modelo.
# ============================================================
@receiver(post_save, sender=Usuario, dispatch_uid="crear_carro_del_cliente")
def crear_carro_del_cliente(sender, instance, created, **kwargs):
    """Crea el carro persistente del cliente en cuanto existe su cuenta."""
    if instance.rol != Rol.CLIENTE:
        return
    Carro.objects.get_or_create(usuario=instance)
