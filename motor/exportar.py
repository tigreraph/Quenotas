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
        "Quenotas",
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


def _latin1(texto) -> str:
    """Las fuentes básicas de fpdf2 solo aceptan Latin-1. Un título de
    YouTube con ♪, guion largo o comillas tipográficas reventaría el PDF."""
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def a_pdf(resultado, ruta) -> Path:
    """PDF pensado para imprimir y poner en el atril."""
    from fpdf import FPDF

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    desplazamiento = resultado.fragmento.inicio_s

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1(resultado.fragmento.titulo or "Sin título"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Fragmento {formato_tiempo(resultado.fragmento.inicio_s)} a "
        f"{formato_tiempo(resultado.fragmento.fin_s)}   |   "
        f"{resultado.analisis.modelo_afinacion}   |   "
        f"separación {resultado.analisis.separacion}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    if not resultado.frases:
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 8, "No se detectaron notas en este fragmento.",
                 new_x="LMARGIN", new_y="NEXT")

    for frase in resultado.frases:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0, 8,
            f"Frase {frase.indice}   "
            f"({formato_tiempo(desplazamiento + frase.inicio_s)} a "
            f"{formato_tiempo(desplazamiento + frase.fin_s)})",
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_font("Courier", "B", 10)
        for etiqueta, ancho in (("#", 14), ("Nota", 22), ("Inicio", 26),
                                ("Duración", 26), ("Confianza", 26)):
            pdf.cell(ancho, 6, etiqueta, border="B")
        pdf.ln()
        pdf.set_font("Courier", "", 10)
        for nota in frase.notas:
            pdf.cell(14, 6, str(nota.orden))
            pdf.cell(22, 6, nota.nombre)
            pdf.cell(26, 6, formato_tiempo(desplazamiento + nota.inicio_s))
            pdf.cell(26, 6, f"{nota.duracion_s:.2f} s")
            pdf.cell(26, 6, etiqueta_confianza(nota.confianza))
            pdf.ln()
        pdf.ln(3)

    if resultado.avisos:
        pdf.set_font("Helvetica", "I", 9)
        for aviso in resultado.avisos:
            pdf.multi_cell(0, 5, _latin1(f"Aviso: {aviso}"))

    pdf.output(str(ruta))
    return ruta


def sonificar(frases, ruta, duracion_total_s: float, sr: int = 44100,
              amplitud: float = 0.3, rampa_s: float = 0.005) -> Path:
    """Convierte las notas detectadas en tonos simples alineados con el fragmento."""
    import numpy as np

    from motor.audio import escribir_wav
    from motor.contrato import midi_a_hz

    total = max(1, int(round(duracion_total_s * sr)))
    senal = np.zeros(total, dtype=np.float32)
    for frase in frases:
        for nota in frase.notas:
            muestras = int(round(nota.duracion_s * sr))
            if muestras <= 0:
                continue
            t = np.arange(muestras) / sr
            onda = amplitud * np.sin(2 * np.pi * midi_a_hz(nota.midi) * t)
            rampa = min(int(rampa_s * sr), muestras // 2)
            if rampa > 0:
                onda[:rampa] *= np.linspace(0.0, 1.0, rampa)
                onda[-rampa:] *= np.linspace(1.0, 0.0, rampa)
            inicio = int(round(nota.inicio_s * sr))
            fin = min(inicio + muestras, total)
            if inicio >= total:
                continue
            senal[inicio:fin] += onda[: fin - inicio].astype(np.float32)
    return escribir_wav(ruta, np.clip(senal, -1.0, 1.0), sr)
