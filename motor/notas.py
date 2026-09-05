"""Conversión de una curva de afinación continua en notas discretas.

Es el corazón del proyecto. Recibe lo que produce el detector de afinación
(frecuencia y confianza por trama) y devuelve notas con nombre, inicio,
duración, confianza y desviación en cents.
"""
from __future__ import annotations

import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from motor.contrato import Frase, Nota, hz_a_midi, midi_a_nombre


def _mediana_movil(valores: np.ndarray, ventana: int) -> np.ndarray:
    """Mediana deslizante que ignora los nan. La ventana debe ser impar."""
    if ventana <= 1:
        return valores.copy()
    if ventana % 2 == 0:
        raise ValueError("la ventana de mediana debe ser impar")
    mitad = ventana // 2
    relleno = np.pad(valores, mitad, mode="edge")
    ventanas = sliding_window_view(relleno, ventana)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(ventanas, axis=-1)


def _tramos(alturas: np.ndarray):
    """Corta la serie en tramos consecutivos de igual valor.

    Devuelve una lista de (inicio, fin_exclusivo, valor_o_None).
    """
    tramos = []
    indice = 0
    total = len(alturas)
    while indice < total:
        valor = alturas[indice]
        siguiente = indice + 1
        if np.isnan(valor):
            while siguiente < total and np.isnan(alturas[siguiente]):
                siguiente += 1
            tramos.append((indice, siguiente, None))
        else:
            while siguiente < total and alturas[siguiente] == valor:
                siguiente += 1
            tramos.append((indice, siguiente, int(valor)))
        indice = siguiente
    return tramos


def _absorber_transitorios(alturas, hop_s, estabilidad_min_s):
    """Elimina los tramos demasiado cortos para ser una nota real.

    Si el tramo corto está entre dos tramos de la misma altura, se funde con
    ellos. Si no, se descarta como silencio. Se repite hasta que no queda
    ningún tramo corto, lo cual termina siempre porque cada pasada elimina al
    menos uno y nunca crea uno nuevo.
    """
    minimo = max(1, int(round(estabilidad_min_s / hop_s)))
    salida = alturas.copy()
    while True:
        tramos = _tramos(salida)
        for posicion, (inicio, fin, valor) in enumerate(tramos):
            if valor is None or fin - inicio >= minimo:
                continue
            anterior = tramos[posicion - 1][2] if posicion > 0 else None
            siguiente = tramos[posicion + 1][2] if posicion < len(tramos) - 1 else None
            if anterior is not None and anterior == siguiente:
                salida[inicio:fin] = anterior
            else:
                salida[inicio:fin] = np.nan
            break
        else:
            return salida


CONCENTRACION_MINIMA = 0.5


def estimar_afinacion(f0_hz, confianza, umbral_confianza: float = 0.5) -> float:
    """Desvío global del instrumento respecto a la rejilla de semitonos.

    Media circular de la parte fraccionaria del MIDI continuo sobre las
    tramas con voz. Si las tramas no se concentran (por ejemplo, vibrato
    que barre medio semitono a cada lado), devuelve 0.0 y no se corrige nada.
    """
    f0_hz = np.asarray(f0_hz, dtype=float)
    confianza = np.asarray(confianza, dtype=float)
    midi = hz_a_midi(f0_hz)[confianza >= umbral_confianza]
    midi = midi[~np.isnan(midi)]
    if len(midi) == 0:
        return 0.0
    angulos = 2 * np.pi * (midi - np.round(midi))
    vector = complex(np.mean(np.cos(angulos)), np.mean(np.sin(angulos)))
    if abs(vector) < CONCENTRACION_MINIMA:
        return 0.0
    return float(np.angle(vector) / (2 * np.pi))


def curva_a_notas(
    f0_hz,
    confianza,
    hop_s: float,
    umbral_confianza: float = 0.5,
    ventana_mediana: int = 5,
    estabilidad_min_s: float = 0.05,
    duracion_min_s: float = 0.06,
    afinacion: float = 0.0,
) -> list[Nota]:
    f0_hz = np.asarray(f0_hz, dtype=float)
    confianza = np.asarray(confianza, dtype=float)
    if len(f0_hz) != len(confianza):
        raise ValueError("f0_hz y confianza deben tener la misma longitud")
    if len(f0_hz) == 0:
        return []

    hay_voz = confianza >= umbral_confianza
    midi_continuo = np.where(hay_voz, hz_a_midi(f0_hz), np.nan)
    # El desvío global se resta solo para decidir el nombre de la nota; los
    # cents se calculan más abajo sobre midi_continuo sin corregir.
    suavizado = _mediana_movil(midi_continuo - afinacion, ventana_mediana)
    suavizado = np.where(hay_voz, suavizado, np.nan)
    redondeado = np.where(np.isnan(suavizado), np.nan, np.round(suavizado))
    redondeado = _absorber_transitorios(redondeado, hop_s, estabilidad_min_s)

    minimo_tramas = max(1, int(round(duracion_min_s / hop_s)))
    notas: list[Nota] = []
    for inicio, fin, valor in _tramos(redondeado):
        if valor is None or fin - inicio < minimo_tramas:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mediana_real = np.nanmedian(midi_continuo[inicio:fin])
        desviacion = 0 if np.isnan(mediana_real) else int(round((mediana_real - valor) * 100))
        notas.append(
            Nota(
                orden=len(notas) + 1,
                nombre=midi_a_nombre(valor),
                midi=valor,
                inicio_s=round(inicio * hop_s, 4),
                duracion_s=round((fin - inicio) * hop_s, 4),
                confianza=round(float(np.mean(confianza[inicio:fin])), 4),
                cents=desviacion,
            )
        )
    return notas


def agrupar_en_frases(notas, silencio_min_s: float = 0.6) -> list[Frase]:
    """Corta la lista de notas en frases usando los silencios largos."""
    if not notas:
        return []
    grupos: list[list[Nota]] = [[notas[0]]]
    for nota in notas[1:]:
        anterior = grupos[-1][-1]
        if nota.inicio_s - anterior.fin_s > silencio_min_s:
            grupos.append([])
        grupos[-1].append(nota)
    return [
        Frase(
            indice=posicion + 1,
            inicio_s=grupo[0].inicio_s,
            fin_s=grupo[-1].fin_s,
            notas=tuple(grupo),
        )
        for posicion, grupo in enumerate(grupos)
    ]
