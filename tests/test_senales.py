import numpy as np

from tests.senales import curva, secuencia, silencio, tono


def test_la_curva_alterna_voz_y_silencio():
    f0, confianza = curva([(69, 0.5), (None, 0.2), (71, 0.5)], hop_s=0.01)
    assert len(f0) == len(confianza) == 120
    assert np.allclose(f0[:50], 440.0, atol=0.01)
    assert np.all(confianza[50:70] < 0.5)
    assert np.all(f0[50:70] == 0)
    assert np.all(confianza[70:] > 0.5)


def test_la_curva_acepta_midi_flotante():
    f0, _ = curva([(69.25, 0.1)], hop_s=0.01)
    esperado = 440.0 * 2 ** (0.25 / 12)
    assert np.allclose(f0, esperado, atol=0.01)


def test_la_curva_acepta_una_funcion_para_el_vibrato():
    f0, _ = curva([(lambda i, n: 69 + 0.5 * np.sin(2 * np.pi * i / 20), 0.4)], hop_s=0.01)
    assert len(f0) == 40
    assert f0.max() > f0.min()


def test_el_tono_tiene_la_longitud_pedida():
    assert len(tono(440.0, 0.5, sr=16000)) == 8000
    assert len(silencio(0.25, sr=16000)) == 4000


def test_la_secuencia_concatena_tramos():
    señal = secuencia([(440.0, 0.5), (None, 0.2), (494.0, 0.5)], sr=16000)
    assert len(señal) == 19200
    assert np.allclose(señal[8000:11200], 0.0)
