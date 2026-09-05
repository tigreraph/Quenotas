"""Parámetros del motor. Nada de esto se escribe a mano en el código.

Se leen de variables de entorno para que la misma carpeta corra en una
laptop con GPU y en un servidor sin ella cambiando solo la configuración.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def resolver_dispositivo(preferencia: str = "auto") -> str:
    """Devuelve 'cuda' o 'cpu'. 'auto' usa CUDA solo si está disponible."""
    if preferencia in {"cpu", "cuda"}:
        return preferencia
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


@dataclass(frozen=True)
class Config:
    media_dir: Path = RAIZ / "media"
    dispositivo: str = "auto"
    hop_ms: int = 10
    fmin_hz: float = 261.63          # C4
    fmax_hz: float = 1567.98         # G6
    umbral_confianza: float = 0.5
    ventana_mediana: int = 5
    estabilidad_min_s: float = 0.05
    duracion_min_s: float = 0.06
    silencio_frase_s: float = 0.6
    max_fragmento_s: float = 180.0
    modelo_afinacion: str = "full"
    modelo_separacion: str = "htdemucs"
    segmento_demucs: float = 6.0     # Demucs lo recomienda por debajo de 8 GB de VRAM

    def __post_init__(self):
        if self.ventana_mediana % 2 == 0:
            raise ValueError("la ventana de mediana debe ser impar")
        if self.fmin_hz >= self.fmax_hz:
            raise ValueError("fmin_hz debe ser menor que fmax_hz")

    @staticmethod
    def desde_entorno(entorno=None) -> "Config":
        """Lee SACANOTAS_<CAMPO> para cada campo; lo que no esté, queda en su
        valor por defecto de la dataclass. Los tipos salen de la anotación."""
        entorno = os.environ if entorno is None else entorno
        conversores = {"Path": Path, "str": str, "int": int, "float": float}
        valores = {}
        for nombre, campo in Config.__dataclass_fields__.items():
            bruto = entorno.get(f"SACANOTAS_{nombre.upper()}")
            if nombre == "media_dir":
                bruto = entorno.get("SACANOTAS_MEDIA", bruto)
            if bruto is not None:
                valores[nombre] = conversores[campo.type](bruto)
        return Config(**valores)
