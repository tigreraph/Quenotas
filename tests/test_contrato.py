import numpy as np
import pytest

from motor.contrato import (
    Fragmento,
    Frase,
    Nota,
    ParametrosAnalisis,
    Resultado,
    etiqueta_confianza,
    formato_tiempo,
    hz_a_midi,
    midi_a_hz,
    midi_a_nombre,
    nombre_a_midi,
)


def test_formato_tiempo():
    assert formato_tiempo(0.0) == "0:00.0"
    assert formato_tiempo(30.44) == "0:30.4"
    assert formato_tiempo(90.0) == "1:30.0"
    assert formato_tiempo(3661.5) == "61:01.5"
    assert formato_tiempo(59.96) == "1:00.0"


def test_etiqueta_confianza():
    assert etiqueta_confianza(0.93) == "alta"
    assert etiqueta_confianza(0.71) == "media"
    assert etiqueta_confianza(0.40) == "baja"


@pytest.mark.parametrize(
    "midi,nombre",
    [(60, "C4"), (67, "G4"), (69, "A4"), (71, "B4"), (91, "G6"), (61, "C#4")],
)
def test_conversion_midi_nombre_ida_y_vuelta(midi, nombre):
    assert midi_a_nombre(midi) == nombre
    assert nombre_a_midi(nombre) == midi


def test_hz_a_midi_reconoce_el_la_de_referencia():
    assert hz_a_midi(440.0) == pytest.approx(69.0)
    assert midi_a_hz(69) == pytest.approx(440.0)


def test_hz_a_midi_devuelve_nan_para_silencio():
    salida = hz_a_midi(np.array([440.0, 0.0, -1.0]))
    assert salida[0] == pytest.approx(69.0)
    assert np.isnan(salida[1])
    assert np.isnan(salida[2])


def _resultado_de_ejemplo():
    nota = Nota(orden=1, nombre="G4", midi=67, inicio_s=0.4,
                duracion_s=0.42, confianza=0.93, cents=-12)
    frase = Frase(indice=1, inicio_s=0.4, fin_s=0.82, notas=(nota,))
    return Resultado(
        fragmento=Fragmento(titulo="Prueba", fuente="archivo",
                            referencia="prueba.wav", inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="ninguna", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cpu"),
        frases=(frase,),
        archivos={"midi": "media/x.mid"},
        avisos=("un aviso",),
    )


def test_resultado_va_y_vuelve_de_diccionario():
    original = _resultado_de_ejemplo()
    copia = Resultado.desde_dict(original.a_dict())
    assert copia == original


def test_a_dict_usa_las_claves_del_contrato():
    diccionario = _resultado_de_ejemplo().a_dict()
    assert set(diccionario) == {"fragmento", "analisis", "frases", "archivos", "avisos"}
    assert set(diccionario["frases"][0]["notas"][0]) == {
        "orden", "nombre", "midi", "inicio_s", "duracion_s", "confianza", "cents"
    }


def test_las_notas_son_inmutables():
    nota = _resultado_de_ejemplo().frases[0].notas[0]
    with pytest.raises(Exception):
        nota.midi = 68
