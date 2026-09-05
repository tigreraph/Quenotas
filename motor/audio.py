"""Lectura, recorte y conversión de audio. ffmpeg y ffprobe son externos."""
from __future__ import annotations

import json
import os
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}


class ErrorAudio(Exception):
    """Algo falló al leer, recortar o convertir audio."""


def _ejecutar(comando):
    try:
        return subprocess.run(
            comando, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
        )
    except FileNotFoundError as error:
        raise ErrorAudio(f"no se encontró el programa {comando[0]}") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        raise ErrorAudio(detalle[-1] if detalle else "ffmpeg falló sin mensaje") from error


def duracion_s(ruta) -> float:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"el archivo no existe: {ruta}")
    salida = _ejecutar([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(ruta),
    ])
    try:
        return float(json.loads(salida.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        raise ErrorAudio(f"ffprobe no pudo leer la duración de {ruta.name}") from error


def recortar(entrada, salida, inicio_s: float, fin_s: float, sr: int = 44100) -> Path:
    """Recorta el rango pedido a WAV mono. Valida el rango antes de trabajar."""
    entrada, salida = Path(entrada), Path(salida)
    if fin_s <= inicio_s:
        raise ErrorAudio("el final del fragmento debe ser posterior al inicio")
    if inicio_s < 0:
        raise ErrorAudio("el inicio del fragmento no puede ser negativo")
    total = duracion_s(entrada)
    if fin_s > total + 0.25:
        raise ErrorAudio(
            f"el rango pedido llega hasta {fin_s:.1f} s pero la duración del audio "
            f"es de {total:.1f} s"
        )
    salida.parent.mkdir(parents=True, exist_ok=True)
    _ejecutar([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{inicio_s:.3f}", "-to", f"{fin_s:.3f}",
        "-i", str(entrada),
        "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(salida),
    ])
    if not salida.exists():
        raise ErrorAudio("ffmpeg no generó el recorte")
    return salida


def cargar_mono(ruta) -> tuple[np.ndarray, int]:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"el archivo no existe: {ruta}")
    datos, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    return datos.mean(axis=1), int(sr)


def remuestrear(senal: np.ndarray, sr_origen: int, sr_destino: int) -> np.ndarray:
    if sr_origen == sr_destino:
        return senal
    razon = Fraction(int(sr_destino), int(sr_origen)).limit_denominator(1000)
    return resample_poly(senal, razon.numerator, razon.denominator).astype(np.float32)


def escribir_wav(ruta, senal: np.ndarray, sr: int) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(ruta), np.asarray(senal, dtype=np.float32), int(sr))
    return ruta
