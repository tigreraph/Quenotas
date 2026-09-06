"""Servir audio con soporte de Range.

Sin respuestas 206, saltar dentro de una canción de cinco minutos no
funciona bien en Chrome y no funciona en Safari. FileResponse de Django
no lo hace, así que se hace aquí, para un solo rango por petición.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

_RANGO = re.compile(r"^bytes=(\d*)-(\d*)$")
_TROZO = 64 * 1024

TIPOS_AUDIO = {
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}


def _trozos(ruta: Path, inicio: int, longitud: int):
    with open(ruta, "rb") as archivo:
        archivo.seek(inicio)
        restante = longitud
        while restante > 0:
            datos = archivo.read(min(_TROZO, restante))
            if not datos:
                break
            restante -= len(datos)
            yield datos


def respuesta_audio(ruta, request):
    ruta = Path(ruta)
    tamano = ruta.stat().st_size
    tipo = TIPOS_AUDIO.get(ruta.suffix.lower(), "application/octet-stream")
    coincidencia = _RANGO.match(request.META.get("HTTP_RANGE", ""))

    if not coincidencia or coincidencia.group(1) == coincidencia.group(2) == "":
        respuesta = FileResponse(open(ruta, "rb"), content_type=tipo)
        respuesta["Accept-Ranges"] = "bytes"
        respuesta["Content-Length"] = str(tamano)
        return respuesta

    desde, hasta = coincidencia.groups()
    if desde == "":                       # bytes=-n: los últimos n bytes
        inicio = max(0, tamano - int(hasta))
        fin = tamano - 1
    else:
        inicio = int(desde)
        fin = int(hasta) if hasta else tamano - 1
    fin = min(fin, tamano - 1)
    if inicio >= tamano or inicio > fin:
        respuesta = HttpResponse(status=416)
        respuesta["Content-Range"] = f"bytes */{tamano}"
        return respuesta

    longitud = fin - inicio + 1
    respuesta = StreamingHttpResponse(_trozos(ruta, inicio, longitud), status=206, content_type=tipo)
    respuesta["Content-Range"] = f"bytes {inicio}-{fin}/{tamano}"
    respuesta["Content-Length"] = str(longitud)
    respuesta["Accept-Ranges"] = "bytes"
    return respuesta
