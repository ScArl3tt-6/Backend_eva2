# ============================================================
# usuarios/tokens.py — TOKEN JWT CON CLAIM DE ROL
# Responsabilidad: agregar información del usuario dentro del
# propio token JWT.
#
# Por qué importa: sin el claim "rol", cada petición tendría que
# consultar la base de datos para saber si quien llama es cliente
# o administrador. Con el claim, el rol viaja firmado dentro del
# token y los permisos de usuarios/permisos.py lo leen desde
# request.auth, contrastándolo además con el rol guardado en la
# base (defensa en profundidad: si un administrador es degradado a
# cliente, su token antiguo deja de servir de inmediato).
# ============================================================

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import Token


# ============================================================
# BLOQUE 1 — SERIALIZER DE LOGIN CON CLAIMS ADICIONALES
# Hereda de TokenObtainPairSerializer y sobrescribe get_token()
# para incorporar rol, username, email y nombre completo. Esos
# claims quedan tanto en el access como en el refresh, porque
# get_token() construye el refresh y el access se deriva de él.
# ============================================================
class TokenConRolSerializer(TokenObtainPairSerializer):
    """Emite el par de tokens agregando el rol del usuario como claim."""

    @classmethod
    def get_token(cls, user) -> Token:
        """Construye el token e inserta los claims propios del negocio."""
        token = super().get_token(user)

        # --- Claims propios del proyecto ---
        token["rol"] = user.rol
        token["username"] = user.username
        token["email"] = user.email
        token["nombre_completo"] = user.nombre_completo

        return token

    # ============================================================
    # BLOQUE 2 — RESPUESTA ENRIQUECIDA DEL LOGIN
    # Además de access y refresh, la respuesta entrega el rol y los
    # datos del usuario ya resueltos, para que el cliente no tenga
    # que decodificar el token solo para saber a quién atendió.
    # ============================================================
    def validate(self, attrs):
        """Valida las credenciales y agrega el rol y el usuario a la respuesta."""
        datos = super().validate(attrs)

        datos["rol"] = self.user.rol
        datos["usuario"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "nombre_completo": self.user.nombre_completo,
            "rol": self.user.rol,
            "rol_etiqueta": self.user.get_rol_display(),
            "es_administrador": self.user.es_administrador,
        }
        return datos
