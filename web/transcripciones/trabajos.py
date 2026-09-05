"""Ejecución del análisis fuera del ciclo de la petición HTTP.

Para un solo usuario en local un hilo basta. La pieza está aislada a
propósito: si algún día hubiera varios usuarios, se sustituye por una
cola real sin tocar ni las vistas ni el motor.
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from django.conf import settings
from django.db import connection

from motor.contrato import Fragmento as FragmentoContrato

# Puntos de sustitución para las pruebas. None significa "usar el pipeline
# real", que se importa dentro de las funciones para que esta capa cargue
# aunque motor/pipeline.py todavía no tenga preparar/analizar_preparado.
_PREPARAR = None
_ANALIZAR = None

# Demucs y CREPE no caben dos veces en 4 GB de VRAM. El segundo espera.
UN_ANALISIS_A_LA_VEZ = threading.Semaphore(1)

MENSAJE_INTERRUMPIDO = "El trabajo se interrumpió (se cerró el programa a mitad). Reintenta."


def _preparar_real():
    if _PREPARAR is not None:
        return _PREPARAR
    from motor.pipeline import preparar
    return preparar


def _analizar_real():
    if _ANALIZAR is not None:
        return _ANALIZAR
    from motor.pipeline import analizar_preparado
    return analizar_preparado


def directorio_de(fragmento) -> Path:
    return Path(settings.MEDIA_ROOT) / "fragmentos" / str(fragmento.pk)


def cache_descargas() -> Path:
    """Compartida por todos los fragmentos: una canción se baja una sola vez."""
    return Path(settings.MEDIA_ROOT) / "origen"


def _progreso_de(fragmento_id):
    from .models import Fragmento

    def progreso(mensaje):
        Fragmento.objects.filter(pk=fragmento_id).update(paso=mensaje)

    return progreso


def _marcar_error(fragmento_id, error):
    from .models import Fragmento

    traceback.print_exc()
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.ERROR, paso="", mensaje=str(error)
    )


def ejecutar_preparacion(fragmento_id: int, origen: str) -> None:
    """Descarga y recorta. Deja el fragmento listo para escuchar."""
    from .models import Fragmento

    fragmento = Fragmento.objects.get(pk=fragmento_id)
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PREPARANDO, paso="Preparando", mensaje=""
    )
    try:
        recorte, contrato = _preparar_real()(
            origen=origen,
            inicio_s=fragmento.inicio_s,
            fin_s=fragmento.fin_s,
            directorio_trabajo=directorio_de(fragmento),
            titulo=fragmento.cancion.titulo,
            progreso=_progreso_de(fragmento_id),
            cache_dir=cache_descargas(),
        )
        cancion = fragmento.cancion
        cancion.titulo = contrato.titulo
        cancion.fuente = contrato.fuente
        cancion.referencia = contrato.referencia
        cancion.save()

        fragmento.refresh_from_db()
        fragmento.archivos = {"mezcla_wav": str(recorte)}
        fragmento.estado = Fragmento.PREPARADO
        fragmento.paso = ""
        fragmento.save(update_fields=["archivos", "estado", "paso"])
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def ejecutar_analisis(fragmento_id: int) -> None:
    """Separa, detecta las notas y genera los archivos de salida."""
    from .models import Fragmento

    fragmento = Fragmento.objects.get(pk=fragmento_id)
    recorte = fragmento.archivos.get("mezcla_wav")
    if not recorte:
        _marcar_error(fragmento_id, RuntimeError("el fragmento no tiene recorte preparado"))
        connection.close()
        return

    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    try:
        with UN_ANALISIS_A_LA_VEZ:
            Fragmento.objects.filter(pk=fragmento_id).update(paso="Analizando")
            resultado = _analizar_real()(
                recorte=recorte,
                fragmento=FragmentoContrato(
                    titulo=fragmento.cancion.titulo,
                    fuente=fragmento.cancion.fuente,
                    referencia=fragmento.cancion.referencia,
                    inicio_s=fragmento.inicio_s,
                    fin_s=fragmento.fin_s,
                ),
                separar=fragmento.separar,
                progreso=_progreso_de(fragmento_id),
            )
        fragmento.refresh_from_db()
        fragmento.guardar_resultado(resultado)
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def lanzar_preparacion(fragmento_id: int, origen: str) -> None:
    threading.Thread(
        target=ejecutar_preparacion, args=(fragmento_id, origen), daemon=True
    ).start()


def lanzar_analisis(fragmento_id: int) -> None:
    threading.Thread(target=ejecutar_analisis, args=(fragmento_id,), daemon=True).start()


def recuperar_huerfanos() -> int:
    """Al arrancar: lo que quedó a medias en la sesión anterior pasa a error."""
    from .models import Fragmento

    return Fragmento.objects.filter(
        estado__in=[Fragmento.PREPARANDO, Fragmento.PROCESANDO]
    ).update(estado=Fragmento.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO)
