"""Generación de los archivos que se lleva el usuario.

Todos salen de la misma estructura de datos. Los tiempos guardados en el
contrato son relativos al fragmento; aquí se les suma el desplazamiento
de la canción para que el usuario vea el minuto real.
"""
from __future__ import annotations

from pathlib import Path

from motor.contrato import etiqueta_confianza, formato_tiempo

PROGRAMA_FLAUTA = 73


def a_midi(frases, ruta, programa: int = PROGRAMA_FLAUTA, velocidad: int = 90) -> Path:
    import pretty_midi

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    archivo = pretty_midi.PrettyMIDI()
    instrumento = pretty_midi.Instrument(program=programa, name="melodia")
    for frase in frases:
        for nota in frase.notas:
            instrumento.notes.append(
                pretty_midi.Note(
                    velocity=velocidad,
                    pitch=int(nota.midi),
                    start=float(nota.inicio_s),
                    end=float(nota.inicio_s + nota.duracion_s),
                )
            )
    archivo.instruments.append(instrumento)
    archivo.write(str(ruta))
    return ruta


def _lineas_de_texto(resultado) -> list[str]:
    desplazamiento = resultado.fragmento.inicio_s
    lineas = [
        "SacaNotas",
        f"Canción: {resultado.fragmento.titulo}",
        f"Fuente: {resultado.fragmento.referencia}",
        f"Fragmento: {formato_tiempo(resultado.fragmento.inicio_s)} a "
        f"{formato_tiempo(resultado.fragmento.fin_s)}",
        f"Análisis: separación {resultado.analisis.separacion}, "
        f"{resultado.analisis.modelo_afinacion}, {resultado.analisis.dispositivo}",
        "",
    ]
    if not resultado.frases:
        lineas.append("No se detectaron notas en este fragmento.")
    for frase in resultado.frases:
        lineas.append(
            f"Frase {frase.indice}  ({formato_tiempo(desplazamiento + frase.inicio_s)} a "
            f"{formato_tiempo(desplazamiento + frase.fin_s)})"
        )
        for nota in frase.notas:
            lineas.append(
                f"  {nota.orden:>3}  {nota.nombre:<4} "
                f"{formato_tiempo(desplazamiento + nota.inicio_s):>8}  "
                f"{nota.duracion_s:5.2f} s  confianza {etiqueta_confianza(nota.confianza)}"
            )
        lineas.append("")
    if resultado.avisos:
        lineas.append("Avisos:")
        lineas.extend(f"  - {aviso}" for aviso in resultado.avisos)
    return lineas


def a_txt(resultado, ruta) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(_lineas_de_texto(resultado)) + "\n", encoding="utf-8")
    return ruta
