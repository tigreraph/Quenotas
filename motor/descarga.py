"""Descarga del audio de un video con yt-dlp, con caché por id de video.

Se descarga la pista completa en su formato nativo y el recorte se hace
después con ffmpeg, que es preciso al milisegundo y acepta cualquier
formato. La canción se guarda como <cache_dir>/<id>.<ext> y se reutiliza:
diez fragmentos de la misma canción son una sola descarga.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}
SUFIJOS_A_MEDIAS = {".part", ".ytdl"}
NOMBRE_SIN_ID = "descarga"


class ErrorDescarga(Exception):
    """No se pudo obtener el audio del enlace."""


def _EJECUTAR(comando):  # noqa: N802
    return subprocess.run(
        comando, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
    )


def es_url(texto: str) -> bool:
    return str(texto).strip().lower().startswith(("http://", "https://"))


def obtener_info(url: str) -> tuple[str, str]:
    """(id_del_video, titulo) en una sola llamada. ('', '') si no se puede."""
    try:
        salida = _EJECUTAR([
            sys.executable, "-m", "yt_dlp", "--no-playlist", "--skip-download",
            "--print", "%(id)s", "--print", "%(title)s", url,
        ])
    except Exception:  # noqa: BLE001
        return "", ""
    lineas = [linea.strip() for linea in (salida.stdout or "").splitlines() if linea.strip()]
    if len(lineas) < 2:
        return "", ""
    return lineas[0], lineas[1]


def _en_cache(cache_dir: Path, nombre: str) -> Path | None:
    candidatos = [
        ruta for ruta in sorted(cache_dir.glob(f"{nombre}.*"))
        if ruta.suffix not in SUFIJOS_A_MEDIAS and ruta.is_file()
    ]
    return candidatos[0] if candidatos else None


def descargar_audio(url: str, cache_dir, id_video: str = "") -> Path:
    """Devuelve el audio completo del video, descargándolo solo si no está en caché."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not id_video:
        id_video, _ = obtener_info(url)
    nombre = id_video or NOMBRE_SIN_ID

    if id_video:
        existente = _en_cache(cache_dir, nombre)
        if existente is not None:
            return existente

    plantilla = str(cache_dir / f"{nombre}.%(ext)s")
    comando = [
        sys.executable, "-m", "yt_dlp", "--no-playlist",
        "-f", "bestaudio/best",
        "-o", plantilla, url,
    ]
    try:
        _EJECUTAR(comando)
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        motivo = detalle[-1] if detalle else "yt-dlp falló sin mensaje"
        raise ErrorDescarga(
            f"No se pudo descargar el audio del enlace ({motivo}). "
            f"Sube el archivo de audio directamente y vuelve a intentarlo."
        ) from error
    except FileNotFoundError as error:
        raise ErrorDescarga("yt-dlp no está instalado") from error

    descargado = _en_cache(cache_dir, nombre)
    if descargado is None:
        raise ErrorDescarga(
            "yt-dlp terminó pero no dejó ningún archivo. "
            "Sube el archivo de audio directamente y vuelve a intentarlo."
        )
    return descargado
