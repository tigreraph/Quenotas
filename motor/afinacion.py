"""Detección de la frecuencia fundamental con CREPE.

Devuelve dos series por trama: la frecuencia estimada y la confianza de
esa estimación. La confianza es lo que después permite distinguir el
sonido real del silencio y avisar al usuario de qué notas revisar.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from motor.audio import cargar_mono, remuestrear

SR_CREPE = 16000


def detectar_afinacion(
    ruta_wav,
    fmin_hz: float,
    fmax_hz: float,
    hop_ms: int = 10,
    dispositivo: str = "cpu",
    modelo: str = "full",
) -> tuple[np.ndarray, np.ndarray, float]:
    import torch
    import torchcrepe

    senal, sr = cargar_mono(Path(ruta_wav))
    senal = remuestrear(senal, sr, SR_CREPE)
    tensor = torch.from_numpy(np.ascontiguousarray(senal, dtype=np.float32))[None]

    salto = int(SR_CREPE * hop_ms / 1000)
    f0, confianza = torchcrepe.predict(
        tensor,
        SR_CREPE,
        salto,
        float(fmin_hz),
        float(fmax_hz),
        modelo,
        batch_size=512,
        device=dispositivo,
        return_periodicity=True,
    )
    return (
        f0[0].detach().cpu().numpy().astype(float),
        confianza[0].detach().cpu().numpy().astype(float),
        hop_ms / 1000.0,
    )
