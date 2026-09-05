"""Contrato de datos de SacaNotas.

Todas las piezas del sistema producen y consumen estas estructuras.
Los tiempos son relativos al inicio del fragmento: 0 es el primer
instante del recorte, y el desplazamiento dentro de la canción vive
solo en Fragmento.inicio_s.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import numpy as np

NOMBRES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_PATRON_NOMBRE = re.compile(r"^([A-G]#?)(-?\d+)$")


def midi_a_nombre(midi: int) -> str:
    """67 -> 'G4'. Convención de Do central en C4 = MIDI 60."""
    midi = int(midi)
    return f"{NOMBRES[midi % 12]}{midi // 12 - 1}"


def nombre_a_midi(nombre: str) -> int:
    """'G4' -> 67."""
    coincidencia = _PATRON_NOMBRE.match(nombre.strip())
    if not coincidencia:
        raise ValueError(f"nombre de nota inválido: {nombre!r}")
    clase, octava = coincidencia.groups()
    return NOMBRES.index(clase) + (int(octava) + 1) * 12


def hz_a_midi(hz):
    """Frecuencia a número MIDI continuo. Cero o negativo devuelve nan."""
    valores = np.asarray(hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = 69.0 + 12.0 * np.log2(valores / 440.0)
    resultado = np.where(valores > 0, midi, np.nan)
    return resultado if resultado.ndim else float(resultado)


def midi_a_hz(midi) -> float:
    return float(440.0 * 2.0 ** ((float(midi) - 69.0) / 12.0))


def formato_tiempo(segundos: float) -> str:
    """30.44 -> '0:30.4'. Se redondea a décimas antes de partir en minutos
    para que 59.96 sea '1:00.0' y no '0:60.0'."""
    decimas = int(round(max(0.0, float(segundos)) * 10))
    minutos, resto = divmod(decimas, 600)
    return f"{minutos}:{resto // 10:02d}.{resto % 10}"


def etiqueta_confianza(valor: float) -> str:
    """Traduce la confianza 0..1 a lo que ve el usuario. Único sitio donde
    se decide el corte; la web y el JavaScript reciben la etiqueta hecha."""
    if valor >= 0.85:
        return "alta"
    if valor >= 0.60:
        return "media"
    return "baja"


@dataclass(frozen=True)
class Nota:
    orden: int
    nombre: str
    midi: int
    inicio_s: float
    duracion_s: float
    confianza: float
    cents: int

    @property
    def fin_s(self) -> float:
        return self.inicio_s + self.duracion_s


@dataclass(frozen=True)
class Frase:
    indice: int
    inicio_s: float
    fin_s: float
    notas: tuple[Nota, ...]


@dataclass(frozen=True)
class Fragmento:
    titulo: str
    fuente: str          # "youtube" | "archivo"
    referencia: str
    inicio_s: float
    fin_s: float

    @property
    def duracion_s(self) -> float:
        return self.fin_s - self.inicio_s


@dataclass(frozen=True)
class ParametrosAnalisis:
    separacion: str      # "htdemucs" | "ninguna"
    modelo_afinacion: str
    hop_ms: int
    fmin_hz: float
    fmax_hz: float
    dispositivo: str     # "cuda" | "cpu"
    afinacion_cents: int = 0   # desplazamiento global del instrumento respecto a 440 Hz


@dataclass(frozen=True)
class Resultado:
    fragmento: Fragmento
    analisis: ParametrosAnalisis
    frases: tuple[Frase, ...]
    archivos: dict
    avisos: tuple[str, ...]

    def a_dict(self) -> dict:
        return {
            "fragmento": asdict(self.fragmento),
            "analisis": asdict(self.analisis),
            "frases": [
                {
                    "indice": frase.indice,
                    "inicio_s": frase.inicio_s,
                    "fin_s": frase.fin_s,
                    "notas": [asdict(nota) for nota in frase.notas],
                }
                for frase in self.frases
            ],
            "archivos": dict(self.archivos),
            "avisos": list(self.avisos),
        }

    @staticmethod
    def desde_dict(datos: dict) -> "Resultado":
        return Resultado(
            fragmento=Fragmento(**datos["fragmento"]),
            analisis=ParametrosAnalisis(**datos["analisis"]),
            frases=tuple(
                Frase(
                    indice=frase["indice"],
                    inicio_s=frase["inicio_s"],
                    fin_s=frase["fin_s"],
                    notas=tuple(Nota(**nota) for nota in frase["notas"]),
                )
                for frase in datos["frases"]
            ),
            archivos=dict(datos["archivos"]),
            avisos=tuple(datos["avisos"]),
        )

    @property
    def notas(self) -> tuple[Nota, ...]:
        return tuple(nota for frase in self.frases for nota in frase.notas)
