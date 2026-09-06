"""Ejecución de los trabajos largos fuera del ciclo de la petición HTTP.

Dos trabajos: preparar una canción (descargar o localizar el audio, hacer
la copia de escucha y los picos de la onda) y analizar una frase (recortar
y analizar). Para un solo usuario en local un hilo basta; la pieza está
aislada para poder sustituirla por una cola real sin tocar vistas ni motor.
"""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

from django.conf import settings
from django.db import connection

from motor.contrato import Fragmento as FragmentoContrato

# Puntos de sustitución para las pruebas. None significa "usar el real",
# que se importa dentro de las funciones.
_OBTENER = None            # obtener_audio(origen, cache_dir=, titulo=, progreso=) -> Fuente
_ANALIZAR = None           # analizar_preparado(recorte=, fragmento=, separar=, progreso=) -> Resultado
_RECORTAR = None           # recortar(entrada, salida, inicio_s, fin_s) -> Path
_PREPARAR_ESCUCHA = None   # (ruta_original, directorio) -> (ruta_escucha, duracion_s)

# Demucs y CREPE no caben dos veces en 4 GB de VRAM. El segundo espera.
UN_ANALISIS_A_LA_VEZ = threading.Semaphore(1)

MENSAJE_INTERRUMPIDO = "El trabajo se interrumpió (se cerró el programa a mitad). Reintenta."


def _obtener_real():
    if _OBTENER is not None:
        return _OBTENER
    from motor.pipeline import obtener_audio
    return obtener_audio


def _analizar_real():
    if _ANALIZAR is not None:
        return _ANALIZAR
    from motor.pipeline import analizar_preparado
    return analizar_preparado


def _recortar_real():
    if _RECORTAR is not None:
        return _RECORTAR
    from motor.audio import recortar
    return recortar


def _preparar_escucha(ruta_original, directorio):
    """Copia AAC para el navegador y picos de la onda en JSON. Devuelve (escucha, duración)."""
    if _PREPARAR_ESCUCHA is not None:
        return _PREPARAR_ESCUCHA(ruta_original, directorio)
    from motor.audio import convertir_para_escucha, duracion_s, forma_de_onda

    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    escucha = convertir_para_escucha(ruta_original, directorio / "escucha.m4a")
    (directorio / "onda.json").write_text(json.dumps(forma_de_onda(ruta_original)), encoding="utf-8")
    return escucha, duracion_s(ruta_original)


def directorio_de(fragmento) -> Path:
    return Path(settings.MEDIA_ROOT) / "fragmentos" / str(fragmento.pk)


def directorio_cancion(cancion) -> Path:
    return Path(settings.MEDIA_ROOT) / "canciones" / str(cancion.pk)


def cache_descargas() -> Path:
    """Compartida por todas las canciones: un video se baja una sola vez."""
    return Path(settings.MEDIA_ROOT) / "origen"


def _progreso_de(fragmento_id):
    from .models import Fragmento

    def progreso(mensaje):
        Fragmento.objects.filter(pk=fragmento_id).update(paso=mensaje)

    return progreso


def _progreso_cancion(cancion_id):
    from .models import Cancion

    def progreso(mensaje):
        Cancion.objects.filter(pk=cancion_id).update(paso=mensaje)

    return progreso


def _marcar_error(fragmento_id, error):
    from .models import Fragmento

    traceback.print_exc()
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.ERROR, paso="", mensaje=str(error)
    )


def _marcar_error_cancion(cancion_id, error):
    from .models import Cancion

    traceback.print_exc()
    Cancion.objects.filter(pk=cancion_id).update(
        estado=Cancion.ERROR, paso="", mensaje=str(error)
    )


def ejecutar_preparacion_cancion(cancion_id: int) -> None:
    """Descarga o localiza el audio, hace la copia de escucha y los picos. No usa la GPU."""
    from .models import Cancion

    cancion = Cancion.objects.get(pk=cancion_id)
    Cancion.objects.filter(pk=cancion_id).update(
        estado=Cancion.PREPARANDO, paso="Preparando", mensaje=""
    )
    progreso = _progreso_cancion(cancion_id)
    try:
        fuente = _obtener_real()(
            origen=cancion.origen, cache_dir=cache_descargas(), titulo=cancion.titulo, progreso=progreso,
        )
        progreso("Preparando el audio para escucharlo")
        escucha, duracion = _preparar_escucha(fuente.ruta, directorio_cancion(cancion))
        Cancion.objects.filter(pk=cancion_id).update(
            titulo=fuente.titulo, fuente=fuente.fuente, referencia=fuente.referencia,
            audio_original=str(fuente.ruta), audio_escucha=str(escucha), duracion_s=float(duracion),
            estado=Cancion.LISTA, paso="", mensaje="",
        )
    except Exception as error:  # noqa: BLE001
        _marcar_error_cancion(cancion_id, error)
    finally:
        connection.close()


def ejecutar_frase(fragmento_id: int) -> None:
    """Recorta la frase desde el audio de la canción y la analiza, de a una."""
    from .models import Fragmento

    fragmento = Fragmento.objects.select_related("cancion").get(pk=fragmento_id)
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    progreso = _progreso_de(fragmento_id)
    try:
        with UN_ANALISIS_A_LA_VEZ:
            progreso("Recortando el fragmento")
            recorte = _recortar_real()(
                fragmento.cancion.audio_original,
                directorio_de(fragmento) / "mezcla.wav",
                fragmento.inicio_s,
                fragmento.fin_s,
            )
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
                progreso=progreso,
            )
        fragmento.refresh_from_db()
        fragmento.guardar_resultado(resultado)
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def lanzar_preparacion_cancion(cancion_id: int) -> None:
    threading.Thread(target=ejecutar_preparacion_cancion, args=(cancion_id,), daemon=True).start()


def lanzar_frase(fragmento_id: int) -> None:
    threading.Thread(target=ejecutar_frase, args=(fragmento_id,), daemon=True).start()


# Alias provisionales: las vistas de la tarea 17 del plan anterior los usan
# hasta que la tarea 6 de este plan las sustituya. Se eliminan entonces.
def lanzar_preparacion(fragmento_id: int, origen: str) -> None:
    lanzar_frase(fragmento_id)


def lanzar_analisis(fragmento_id: int) -> None:
    lanzar_frase(fragmento_id)


def recuperar_huerfanos() -> int:
    """Al arrancar: lo que quedó a medias en la sesión anterior pasa a error."""
    from .models import Cancion, Fragmento

    canciones = Cancion.objects.filter(estado=Cancion.PREPARANDO).update(
        estado=Cancion.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO
    )
    fragmentos = Fragmento.objects.filter(
        estado__in=[Fragmento.PREPARANDO, Fragmento.PROCESANDO]
    ).update(estado=Fragmento.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO)
    return canciones + fragmentos
