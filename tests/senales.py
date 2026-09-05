"""Generadores de señales y curvas sintéticas para las pruebas.

La curva permite probar la conversión a notas sin cargar CREPE: se le da
directamente la secuencia de alturas y confianzas que el detector habría
producido.
"""
from __future__ import annotations

import numpy as np


def curva(tramos, hop_s=0.01, confianza_voz=0.95, confianza_silencio=0.1):
    """Construye (f0_hz, confianza) a partir de tramos (midi_o_None, duracion_s).

    El midi puede ser un número o una función f(indice, total) -> midi, útil
    para simular vibrato y glissandos.
    """
    frecuencias = []
    confianzas = []
    for altura, duracion_s in tramos:
        tramas = int(round(duracion_s / hop_s))
        if altura is None:
            frecuencias.extend([0.0] * tramas)
            confianzas.extend([confianza_silencio] * tramas)
            continue
        for indice in range(tramas):
            midi = altura(indice, tramas) if callable(altura) else float(altura)
            frecuencias.append(440.0 * 2.0 ** ((midi - 69.0) / 12.0))
            confianzas.append(confianza_voz)
    return np.array(frecuencias, dtype=float), np.array(confianzas, dtype=float)


def tono(frecuencia_hz, duracion_s, sr=44100, amplitud=0.5):
    t = np.arange(int(round(duracion_s * sr))) / sr
    return (amplitud * np.sin(2 * np.pi * frecuencia_hz * t)).astype(np.float32)


def silencio(duracion_s, sr=44100):
    return np.zeros(int(round(duracion_s * sr)), dtype=np.float32)


def secuencia(tramos, sr=44100, amplitud=0.5):
    partes = [
        silencio(duracion_s, sr) if frecuencia is None
        else tono(frecuencia, duracion_s, sr, amplitud)
        for frecuencia, duracion_s in tramos
    ]
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)
