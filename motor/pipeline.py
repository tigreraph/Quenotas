"""Orquestación de las etapas del análisis.

En esta fase solo cubre audio ya limpio y recortado. Las etapas de
descarga y separación se añaden más adelante sin cambiar la firma.
"""
from __future__ import annotations

from pathlib import Path

from motor.afinacion import detectar_afinacion
from motor.audio import duracion_s
from motor.config import Config, resolver_dispositivo
from motor.contrato import Fragmento, ParametrosAnalisis, Resultado
from motor.exportar import a_midi, a_pdf, a_txt, sonificar
from motor.notas import agrupar_en_frases, curva_a_notas, estimar_afinacion

# Punto de sustitución para las pruebas: así se puede probar el pipeline
# entero sin cargar CREPE.
_DETECTAR = detectar_afinacion

AFINACION_AVISO_CENTS = 30


class ErrorPipeline(Exception):
    """El análisis no se pudo completar."""


def _avisar(progreso, mensaje):
    if progreso is not None:
        progreso(mensaje)


def analizar_recorte(
    ruta_wav,
    fragmento: Fragmento,
    config: Config | None = None,
    separar: bool = False,
    progreso=None,
    salidas_en=None,
    melodia_wav=None,
) -> Resultado:
    config = config or Config.desde_entorno()
    ruta_wav = Path(ruta_wav)

    duracion = duracion_s(ruta_wav)
    if duracion > config.max_fragmento_s:
        raise ErrorPipeline(
            f"el fragmento dura {duracion:.1f} s y el límite es "
            f"{config.max_fragmento_s:.1f} s. Recorta un trozo más corto."
        )

    dispositivo = resolver_dispositivo(config.dispositivo)
    avisos = []
    if dispositivo == "cpu" and config.dispositivo != "cpu":
        avisos.append("No hay GPU disponible, el análisis corre en CPU y tarda más.")

    _avisar(progreso, "Detectando la afinación")
    f0, confianza, hop_s = _DETECTAR(
        ruta_wav,
        fmin_hz=config.fmin_hz,
        fmax_hz=config.fmax_hz,
        hop_ms=config.hop_ms,
        dispositivo=dispositivo,
        modelo=config.modelo_afinacion,
    )

    _avisar(progreso, "Convirtiendo la curva en notas")
    afinacion = estimar_afinacion(f0, confianza, umbral_confianza=config.umbral_confianza)
    afinacion_cents = int(round(afinacion * 100))
    notas = curva_a_notas(
        f0,
        confianza,
        hop_s=hop_s,
        umbral_confianza=config.umbral_confianza,
        ventana_mediana=config.ventana_mediana,
        estabilidad_min_s=config.estabilidad_min_s,
        duracion_min_s=config.duracion_min_s,
        afinacion=afinacion,
    )
    frases = agrupar_en_frases(notas, silencio_min_s=config.silencio_frase_s)

    if not notas:
        avisos.append(
            "No se detectó ninguna melodía con confianza suficiente. Es probable "
            "que en este rango el instrumento no toque o no destaque sobre la banda."
        )
    elif sum(nota.confianza for nota in notas) / len(notas) < 0.65:
        avisos.append(
            "La confianza media es baja. Revisa las notas al oído antes de darlas "
            "por buenas, o prueba con otro rango donde la melodía destaque más."
        )
    if abs(afinacion_cents) > AFINACION_AVISO_CENTS:
        sentido = "por encima" if afinacion_cents > 0 else "por debajo"
        avisos.append(
            f"El instrumento suena afinado {abs(afinacion_cents)} cents {sentido} "
            f"de la referencia de 440 Hz. Los nombres de las notas ya lo tienen en "
            f"cuenta; si tocas con la quena, ajústala o transpón de oído."
        )

    resultado = Resultado(
        fragmento=fragmento,
        analisis=ParametrosAnalisis(
            separacion=config.modelo_separacion if separar else "ninguna",
            modelo_afinacion=f"crepe:{config.modelo_afinacion}",
            hop_ms=config.hop_ms,
            fmin_hz=config.fmin_hz,
            fmax_hz=config.fmax_hz,
            dispositivo=dispositivo,
            afinacion_cents=afinacion_cents,
        ),
        frases=tuple(frases),
        archivos={},
        avisos=tuple(avisos),
    )

    if salidas_en is None:
        return resultado

    _avisar(progreso, "Generando los archivos de salida")
    salidas = Path(salidas_en)
    salidas.mkdir(parents=True, exist_ok=True)
    archivos = {"mezcla_wav": str(ruta_wav)}
    if melodia_wav is not None:
        archivos["melodia_wav"] = str(melodia_wav)
    avisos_salida = []

    def intentar(clave, etiqueta, generar):
        """Un archivo que falla se omite con aviso; nunca tumba el resultado."""
        try:
            archivos[clave] = str(generar())
        except Exception as error:  # noqa: BLE001
            avisos_salida.append(f"No se pudo generar el {etiqueta} ({error}).")

    intentar("notas_wav", "audio de notas",
             lambda: sonificar(resultado.frases, salidas / "notas.wav", duracion))
    intentar("midi", "MIDI", lambda: a_midi(resultado.frases, salidas / "melodia.mid"))
    intentar("txt", "TXT", lambda: a_txt(resultado, salidas / "notas.txt"))
    intentar("pdf", "PDF", lambda: a_pdf(resultado, salidas / "notas.pdf"))
    return Resultado(
        fragmento=resultado.fragmento,
        analisis=resultado.analisis,
        frases=resultado.frases,
        archivos=archivos,
        avisos=resultado.avisos + tuple(avisos_salida),
    )
