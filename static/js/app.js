/* ============================================================
   app.js — COMPORTAMIENTO DE LA INTERFAZ
   Responsabilidad: los pocos detalles de interacción que el HTML
   no resuelve por sí solo.

   Se usa JavaScript nativo, sin jQuery ni dependencias. Todo lo
   importante (filtros, formularios, cambios de estado) funciona
   con HTML y peticiones normales al servidor: este archivo solo
   agrega comodidades. Si el navegador tuviera JavaScript
   desactivado, el sitio seguiría siendo utilizable por completo.
   ============================================================ */

(function () {
  "use strict";

  // ============================================================
  // BLOQUE 1 — CONFIRMACIÓN ANTES DE UNA ACCIÓN DESTRUCTIVA
  // Los formularios marcados con data-confirmar piden confirmación
  // antes de enviarse (vaciar el carro, cancelar una orden). Las
  // bajas lógicas de las entidades tienen además su propia página
  // de confirmación en el servidor, de modo que la protección no
  // depende solo del navegador.
  // ============================================================
  function activarConfirmaciones() {
    document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
      formulario.addEventListener("submit", function (evento) {
        var mensaje = formulario.getAttribute("data-confirmar");
        if (mensaje && !window.confirm(mensaje)) {
          evento.preventDefault();
        }
      });
    });
  }

  // ============================================================
  // BLOQUE 2 — CUENTA REGRESIVA DE LA PANTALLA DE REDIRECCIÓN
  // Respaldo en JavaScript de la etiqueta <meta http-equiv="refresh">.
  // Si el navegador ignorara el meta, el temporizador igual lleva
  // al inicio; y si el meta funciona, esta cuenta solo muestra los
  // segundos que faltan.
  // ============================================================
  function activarCuentaRegresiva() {
    var contador = document.getElementById("cuenta-regresiva");
    if (!contador) {
      return;
    }

    var segundos = parseInt(contador.getAttribute("data-segundos") || "3", 10);
    var destino = contador.getAttribute("data-destino") || "/";

    var temporizador = window.setInterval(function () {
      segundos -= 1;
      contador.textContent = segundos > 0 ? String(segundos) : "0";

      if (segundos <= 0) {
        window.clearInterval(temporizador);
        window.location.href = destino;
      }
    }, 1000);
  }

  // ============================================================
  // BLOQUE 3 — CIERRE AUTOMÁTICO DE LOS MENSAJES FLASH
  // Los avisos de éxito e información se cierran solos después de
  // ocho segundos. Los de error y advertencia permanecen, porque
  // suelen explicar algo que hay que leer con calma (por ejemplo,
  // qué producto quedó sin stock al intentar pagar).
  // ============================================================
  function activarCierreDeMensajes() {
    document.querySelectorAll(".alert[data-autocerrar]").forEach(function (alerta) {
      window.setTimeout(function () {
        alerta.style.transition = "opacity 400ms ease";
        alerta.style.opacity = "0";
        window.setTimeout(function () {
          alerta.remove();
        }, 420);
      }, 8000);
    });
  }

  // ============================================================
  // BLOQUE 4 — ENVÍO DEL FORMULARIO DE FILTROS AL CAMBIAR UN SELECT
  // En el catálogo y en los listados, elegir una opción de un
  // selector marcado con data-enviar-al-cambiar aplica el filtro de
  // inmediato, sin necesidad de pulsar «Filtrar».
  // ============================================================
  function activarFiltrosAutomaticos() {
    document.querySelectorAll("[data-enviar-al-cambiar]").forEach(function (campo) {
      campo.addEventListener("change", function () {
        if (campo.form) {
          campo.form.submit();
        }
      });
    });
  }

  // ============================================================
  // BLOQUE 5 — ARRANQUE
  // Se espera a que el documento esté listo para que todos los
  // elementos existan al momento de asociar los comportamientos.
  // ============================================================
  function iniciar() {
    activarConfirmaciones();
    activarCuentaRegresiva();
    activarCierreDeMensajes();
    activarFiltrosAutomaticos();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
