"""Orquestación de las etapas del análisis.

En esta fase solo cubre audio ya limpio y recortado. Las etapas de
descarga y separación se añaden más adelante sin cambiar la firma.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from motor.afinacion import detectar_afinacion
from motor.audio import duracion_s
from motor.config import Config, resolver_dispositivo
from motor.contrato import Fragmento, ParametrosAnalisis, Resultado
from motor.exportar import a_midi, a_pdf, a_txt, sonificar
from motor.notas import agrupar_en_frases, curva_a_notas, estimar_afinacion
from motor import descarga as modulo_descarga
from motor import separacion as modulo_separacion
from motor.audio import recortar

# Punto de sustitución para las pruebas: así se puede probar el pipeline
# entero sin cargar CREPE.
_DETECTAR = detectar_afinacion

AFINACION_AVISO_CENTS = 30
CONFIANZA_MEDIA_AVISO = 0.65
TOLERANCIA_LIMITE_S = 0.5


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
    if duracion > config.max_fragmento_s + TOLERANCIA_LIMITE_S:
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
    elif sum(nota.confianza for nota in notas) / len(notas) < CONFIANZA_MEDIA_AVISO:
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
    archivos = {"mezcla_wav": str(ruta_wav)}
    if melodia_wav is not None:
        archivos["melodia_wav"] = str(melodia_wav)
    avisos_salida = []
    try:
        salidas.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        # Sin carpeta no hay dónde escribir, pero las notas ya están: se devuelven.
        return Resultado(
            fragmento=resultado.fragmento,
            analisis=resultado.analisis,
            frases=resultado.frases,
            archivos=archivos,
            avisos=resultado.avisos
            + (f"No se pudo crear la carpeta de salida ({error}); no se generaron archivos.",),
        )

    def intentar(clave, etiqueta, generar):
        """Un archivo que falla se omite con aviso; nunca tumba el resultado."""
        try:
            archivos[clave] = str(generar())
        except Exception as error:  # noqa: BLE001
            avisos_salida.append(f"No se pudo generar el {etiqueta} ({error}).")

    intentar("notas_wav", "audio de notas",
             lambda: sonificar(resultado.frases, salidas / "notas.wav",
                                fragmento.duracion_s))
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


@dataclass(frozen=True)
class Fuente:
    """De dónde salió el audio completo. Es del pipeline, no del contrato."""
    ruta: Path
    titulo: str
    fuente: str          # "youtube" | "archivo"
    referencia: str


def obtener_audio(origen, cache_dir=None, titulo: str = "", progreso=None) -> Fuente:
    """Descarga (con caché por id de video) o localiza el archivo. No recorta."""
    cache_dir = Path(cache_dir) if cache_dir else Config.desde_entorno().media_dir / "origen"
    if modulo_descarga.es_url(str(origen)):
        referencia = str(origen)
        _avisar(progreso, "Consultando el video")
        id_video, titulo_remoto = modulo_descarga.obtener_info(referencia)
        _avisar(progreso, "Descargando el audio")
        ruta = modulo_descarga.descargar_audio(referencia, cache_dir, id_video=id_video)
        return Fuente(
            ruta=Path(ruta), titulo=titulo or titulo_remoto or "Sin título",
            fuente="youtube", referencia=referencia,
        )
    ruta = Path(str(origen))
    if not str(origen).strip() or not ruta.is_file():
        raise ErrorPipeline(f"el archivo no existe: {ruta}")
    return Fuente(ruta=ruta, titulo=titulo or ruta.stem, fuente="archivo", referencia=ruta.name)


def preparar(
    origen,
    inicio_s: float,
    fin_s: float,
    directorio_trabajo,
    titulo: str = "",
    progreso=None,
    cache_dir=None,
) -> tuple[Path, Fragmento]:
    """Obtiene el audio y recorta el rango. Devuelve (recorte, fragmento).

    Para consola y pruebas. La aplicación web ya no la usa: obtiene el audio
    una vez por canción con obtener_audio y recorta cada frase aparte.
    """
    trabajo = Path(directorio_trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    fuente = obtener_audio(origen, cache_dir=cache_dir, titulo=titulo, progreso=progreso)
    _avisar(progreso, "Recortando el fragmento")
    recorte = recortar(fuente.ruta, trabajo / "mezcla.wav", inicio_s, fin_s)
    fragmento = Fragmento(
        titulo=fuente.titulo, fuente=fuente.fuente, referencia=fuente.referencia,
        inicio_s=float(inicio_s), fin_s=float(fin_s),
    )
    return recorte, fragmento


def _separar_con_respaldo(recorte, trabajo, config, progreso):
    """Devuelve (ruta_melodia_o_None, avisos).

    Primero en el dispositivo configurado. Si se queda sin memoria de video,
    reintenta en CPU (lo manda la sección 10 del diseño). Solo si también
    falla ahí se renuncia a separar.
    """
    avisos = []
    dispositivo = resolver_dispositivo(config.dispositivo)
    intentos = [dispositivo] + (["cpu"] if dispositivo == "cuda" else [])
    ultimo_error = None
    reintento_cpu = False
    for indice, actual in enumerate(intentos):
        _avisar(progreso, "Separando la pista melódica"
                + (" (en CPU, tarda más)" if indice > 0 else ""))
        try:
            melodia = modulo_separacion.separar_melodia(
                recorte,
                trabajo / "separado",
                dispositivo=actual,
                modelo=config.modelo_separacion,
                segmento=config.segmento_demucs if actual == "cuda" else None,
            )
        except modulo_separacion.ErrorSeparacion as error:
            ultimo_error = error
            if actual == "cuda" and error.sin_memoria:
                reintento_cpu = True
                continue
            break
        else:
            # El aviso de "corrió en CPU" solo tiene sentido si el reintento
            # en CPU tuvo éxito; si CUDA no falló, no hubo reintento.
            if actual == "cpu" and reintento_cpu:
                avisos.append(
                    "La tarjeta de video se quedó sin memoria; la separación "
                    "corrió en CPU y tardó más."
                )
            return melodia, avisos
    avisos.append(
        f"La separación falló y se analizó la mezcla completa ({ultimo_error}). "
        f"El resultado puede mezclar notas de otros instrumentos."
    )
    return None, avisos


def analizar_preparado(
    recorte,
    fragmento: Fragmento,
    config: Config | None = None,
    separar: bool = True,
    progreso=None,
) -> Resultado:
    """Segunda mitad: separación, detección, notas y archivos de salida."""
    config = config or Config.desde_entorno()
    recorte = Path(recorte)
    trabajo = recorte.parent

    avisos_previos = []
    melodia = None
    if separar:
        melodia, avisos_previos = _separar_con_respaldo(recorte, trabajo, config, progreso)
        separar = melodia is not None

    resultado = analizar_recorte(
        melodia or recorte,
        fragmento,
        config=config,
        separar=separar,
        progreso=progreso,
        salidas_en=trabajo,
        melodia_wav=melodia,
    )
    archivos = dict(resultado.archivos)
    archivos["mezcla_wav"] = str(recorte)
    return Resultado(
        fragmento=resultado.fragmento,
        analisis=resultado.analisis,
        frases=resultado.frases,
        archivos=archivos,
        avisos=tuple(avisos_previos) + resultado.avisos,
    )


def analizar_fuente(
    origen,
    inicio_s: float,
    fin_s: float,
    directorio_trabajo,
    config: Config | None = None,
    separar: bool = True,
    titulo: str = "",
    progreso=None,
    cache_dir=None,
) -> Resultado:
    """Las dos mitades encadenadas. Para consola y pruebas."""
    recorte, fragmento = preparar(
        origen, inicio_s, fin_s, directorio_trabajo, titulo=titulo, progreso=progreso,
        cache_dir=cache_dir,
    )
    return analizar_preparado(
        recorte, fragmento, config=config, separar=separar, progreso=progreso
    )
