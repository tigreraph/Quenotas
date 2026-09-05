import numpy as np
import pytest
import soundfile as sf

from motor.afinacion import SR_CREPE, detectar_afinacion
from tests.senales import secuencia


@pytest.fixture
def wav_la_y_si(tmp_path):
    ruta = tmp_path / "la_si.wav"
    señal = secuencia([(440.0, 0.6), (None, 0.3), (493.88, 0.6)], sr=44100)
    sf.write(ruta, señal, 44100)
    return ruta


@pytest.mark.lento
def test_detecta_el_la_de_referencia(wav_la_y_si):
    f0, confianza, hop_s = detectar_afinacion(
        wav_la_y_si, fmin_hz=200.0, fmax_hz=1000.0, hop_ms=10, dispositivo="cpu"
    )
    assert hop_s == pytest.approx(0.01)
    assert len(f0) == len(confianza)
    seguro = confianza > 0.5
    assert seguro.sum() > 50
    primera_mitad = f0[: len(f0) // 3][seguro[: len(f0) // 3]]
    assert np.median(primera_mitad) == pytest.approx(440.0, rel=0.02)


@pytest.mark.lento
def test_la_cantidad_de_tramas_corresponde_a_la_duracion(wav_la_y_si):
    f0, _, hop_s = detectar_afinacion(
        wav_la_y_si, fmin_hz=200.0, fmax_hz=1000.0, dispositivo="cpu"
    )
    assert len(f0) * hop_s == pytest.approx(1.5, abs=0.1)


def test_el_salto_en_muestras_es_coherente_con_la_frecuencia_de_crepe():
    assert SR_CREPE == 16000
    assert int(SR_CREPE * 10 / 1000) == 160
