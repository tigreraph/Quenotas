"""Aislamiento de la pista melódica con Demucs.

Un instrumento de viento no es voz, ni bajo, ni batería, así que Demucs lo
deja en la pista 'other' junto con guitarras y charango. Esa es la que se
entrega al detector de afinación.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}
PISTA_MELODICA = "other.wav"


class ErrorSeparacion(Exception):
    """Demucs no pudo separar el audio."""

    @property
    def sin_memoria(self) -> bool:
        return "out of memory" in str(self).lower()


def _EJECUTAR(comando):  # noqa: N802
    return subprocess.run(
        comando, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
    )


def separar_melodia(ruta_wav, directorio_salida, dispositivo: str = "cpu",
                    modelo: str = "htdemucs_6s", segmento=None) -> Path:
    ruta_wav = Path(ruta_wav)
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)

    comando = [
        sys.executable, "-m", "demucs",
        "-n", modelo,
        "-d", dispositivo,
        "--out", str(directorio_salida),
    ]
    if segmento is not None:
        comando += ["--segment", f"{segmento:g}"]
    comando.append(str(ruta_wav))
    try:
        _EJECUTAR(comando)
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        motivo = detalle[-1] if detalle else "demucs falló sin mensaje"
        raise ErrorSeparacion(f"La separación falló: {motivo}") from error
    except FileNotFoundError as error:
        raise ErrorSeparacion("demucs no está instalado") from error

    destino = directorio_salida / modelo / ruta_wav.stem / PISTA_MELODICA
    if not destino.exists():
        raise ErrorSeparacion(
            f"Demucs terminó pero no se encontró {destino}. "
            f"Prueba marcando la casilla de audio limpio para saltar la separación."
        )
    return destino
