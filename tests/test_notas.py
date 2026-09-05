import numpy as np
import pytest

from motor.notas import agrupar_en_frases, curva_a_notas, estimar_afinacion
from tests.senales import curva

HOP = 0.01


def _analizar(tramos, **opciones):
    f0, confianza = curva(tramos, hop_s=HOP)
    return curva_a_notas(f0, confianza, hop_s=HOP, **opciones)


def _analizar_con_afinacion(tramos, **opciones):
    """Lo que hace el pipeline: estimar el desvío global y aplicarlo."""
    f0, confianza = curva(tramos, hop_s=HOP)
    afinacion = estimar_afinacion(f0, confianza)
    return curva_a_notas(f0, confianza, hop_s=HOP, afinacion=afinacion, **opciones)


def test_estimar_afinacion_detecta_un_desvio_global():
    f0, confianza = curva([(69.3, 0.5), (71.3, 0.5), (72.3, 0.5)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == pytest.approx(0.3, abs=0.02)


def test_estimar_afinacion_ignora_el_vibrato_simetrico():
    def vibrato(indice, total):
        return 69 + 0.5 * np.sin(2 * np.pi * indice / 20)

    f0, confianza = curva([(vibrato, 1.0)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == 0.0


def test_estimar_afinacion_en_silencio_es_cero():
    f0, confianza = curva([(None, 0.5)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == 0.0


def test_una_nota_en_la_frontera_del_semitono_no_se_parte():
    """Instrumento 50 cents desplazado con una oscilación lenta y pequeña:
    sin compensar, el redondeo alterna entre 68 y 69 y salen muchas notas."""
    def en_la_frontera(indice, total):
        return 68.5 + 0.04 * np.sin(2 * np.pi * indice / 12)

    sin_compensar = _analizar([(en_la_frontera, 0.8)])
    assert len(sin_compensar) > 1

    notas = _analizar_con_afinacion([(en_la_frontera, 0.8)])
    assert len(notas) == 1
    assert notas[0].nombre in {"G#4", "A4"}
    assert notas[0].duracion_s == pytest.approx(0.8, abs=0.03)
    assert abs(notas[0].cents) == pytest.approx(50, abs=5)


def test_dos_notas_separadas_por_silencio():
    notas = _analizar([(69, 0.5), (None, 0.2), (71, 0.5)])
    assert [nota.nombre for nota in notas] == ["A4", "B4"]
    assert notas[0].inicio_s == pytest.approx(0.0, abs=0.02)
    assert notas[0].duracion_s == pytest.approx(0.5, abs=0.03)
    assert notas[1].inicio_s == pytest.approx(0.7, abs=0.02)
    assert [nota.orden for nota in notas] == [1, 2]


def test_notas_consecutivas_sin_silencio_se_separan_por_el_cambio_de_altura():
    notas = _analizar([(69, 0.4), (71, 0.4), (72, 0.4)])
    assert [nota.nombre for nota in notas] == ["A4", "B4", "C5"]


def test_el_vibrato_no_parte_la_nota():
    def vibrato(indice, total):
        return 69 + 0.5 * np.sin(2 * np.pi * indice / 20)

    notas = _analizar([(vibrato, 1.0)])
    assert len(notas) == 1
    assert notas[0].nombre == "A4"
    assert notas[0].duracion_s == pytest.approx(1.0, abs=0.05)


def test_un_pico_espurio_se_absorbe_entre_dos_tramos_iguales():
    notas = _analizar([(69, 0.3), (76, 0.02), (69, 0.3)])
    assert len(notas) == 1
    assert notas[0].nombre == "A4"
    assert notas[0].duracion_s == pytest.approx(0.62, abs=0.03)


def test_un_tramo_demasiado_corto_entre_alturas_distintas_se_descarta():
    notas = _analizar([(69, 0.3), (76, 0.02), (72, 0.3)])
    assert [nota.nombre for nota in notas] == ["A4", "C5"]


def test_una_nota_mas_corta_que_el_minimo_se_descarta():
    notas = _analizar([(69, 0.03), (None, 0.3), (71, 0.4)])
    assert [nota.nombre for nota in notas] == ["B4"]


def test_la_confianza_baja_cuenta_como_silencio():
    f0, confianza = curva([(69, 0.5), (71, 0.5)], hop_s=HOP)
    confianza[50:] = 0.2
    notas = curva_a_notas(f0, confianza, hop_s=HOP)
    assert [nota.nombre for nota in notas] == ["A4"]


def test_la_desviacion_en_cents_se_reporta():
    notas = _analizar([(69.25, 0.5)])
    assert notas[0].nombre == "A4"
    assert notas[0].cents == pytest.approx(25, abs=2)


def test_la_confianza_de_la_nota_es_el_promedio_de_sus_tramas():
    notas = _analizar([(69, 0.5)])
    assert notas[0].confianza == pytest.approx(0.95, abs=0.01)


def test_una_curva_toda_en_silencio_no_devuelve_notas():
    assert _analizar([(None, 1.0)]) == []


def test_las_frases_se_cortan_en_los_silencios_largos():
    notas = _analizar([(69, 0.4), (None, 1.0), (71, 0.4), (None, 0.1), (72, 0.4)])
    frases = agrupar_en_frases(notas, silencio_min_s=0.6)
    assert [frase.indice for frase in frases] == [1, 2]
    assert [nota.nombre for nota in frases[0].notas] == ["A4"]
    assert [nota.nombre for nota in frases[1].notas] == ["B4", "C5"]
    assert frases[1].inicio_s == pytest.approx(frases[1].notas[0].inicio_s)
    assert frases[1].fin_s == pytest.approx(frases[1].notas[-1].fin_s)


def test_agrupar_sin_notas_no_devuelve_frases():
    assert agrupar_en_frases([]) == []
