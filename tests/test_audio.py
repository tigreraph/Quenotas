import numpy as np
import pytest
import soundfile as sf

from motor.audio import (
    ErrorAudio,
    cargar_mono,
    duracion_s,
    escribir_wav,
    recortar,
    remuestrear,
)
from tests.senales import secuencia


@pytest.fixture
def wav_de_tres_segundos(tmp_path):
    ruta = tmp_path / "origen.wav"
    señal = secuencia([(440.0, 3.0)], sr=44100)
    sf.write(ruta, señal, 44100)
    return ruta


def test_duracion_lee_el_archivo(wav_de_tres_segundos):
    assert duracion_s(wav_de_tres_segundos) == pytest.approx(3.0, abs=0.05)


def test_duracion_falla_con_claridad_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(ErrorAudio):
        duracion_s(tmp_path / "no_existe.wav")


def test_recortar_produce_la_duracion_pedida(wav_de_tres_segundos, tmp_path):
    salida = recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 1.0, 2.5)
    assert salida.exists()
    assert duracion_s(salida) == pytest.approx(1.5, abs=0.05)


def test_recortar_rechaza_un_rango_fuera_del_audio(wav_de_tres_segundos, tmp_path):
    with pytest.raises(ErrorAudio) as error:
        recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 1.0, 10.0)
    assert "duración" in str(error.value)


def test_recortar_rechaza_un_rango_invertido(wav_de_tres_segundos, tmp_path):
    with pytest.raises(ErrorAudio):
        recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 2.0, 1.0)


def test_cargar_mono_promedia_los_canales(tmp_path):
    ruta = tmp_path / "estereo.wav"
    izquierda = np.ones(1000, dtype=np.float32)
    derecha = np.full(1000, -1.0, dtype=np.float32)
    sf.write(ruta, np.stack([izquierda, derecha], axis=1), 16000, subtype="FLOAT")
    señal, sr = cargar_mono(ruta)
    assert sr == 16000
    assert señal.ndim == 1
    assert np.allclose(señal, 0.0, atol=1e-6)


def test_remuestrear_cambia_la_longitud_proporcionalmente():
    señal = secuencia([(440.0, 1.0)], sr=44100)
    salida = remuestrear(señal, 44100, 16000)
    assert len(salida) == pytest.approx(16000, abs=50)


def test_remuestrear_no_toca_la_senal_si_la_frecuencia_coincide():
    señal = secuencia([(440.0, 0.1)], sr=16000)
    assert remuestrear(señal, 16000, 16000) is señal


def test_escribir_wav_y_volver_a_leerlo(tmp_path):
    señal = secuencia([(440.0, 0.5)], sr=16000)
    ruta = escribir_wav(tmp_path / "salida.wav", señal, 16000)
    leida, sr = cargar_mono(ruta)
    assert sr == 16000
    assert len(leida) == len(señal)


from motor.audio import convertir_para_escucha, forma_de_onda


def test_la_forma_de_onda_tiene_una_columna_por_pedido_y_va_de_0_a_1(tmp_path):
    ruta = tmp_path / "medio.wav"
    sf.write(ruta, secuencia([(440.0, 1.0), (None, 1.0)], sr=16000), 16000)
    picos = forma_de_onda(ruta, columnas=10)
    assert len(picos) == 10
    assert all(0.0 <= p <= 1.0 for p in picos)
    assert min(picos[:5]) > 0.9          # el tono ocupa la primera mitad
    # La columna 5 contiene el corte y el remuestreo de ffmpeg deja ahí un
    # rizado de hasta un 3 %; el silencio se mide a partir de la siguiente.
    assert max(picos[6:]) < 0.01


def test_la_forma_de_onda_del_silencio_es_todo_ceros(tmp_path):
    ruta = tmp_path / "silencio.wav"
    sf.write(ruta, secuencia([(None, 0.5)], sr=16000), 16000)
    assert forma_de_onda(ruta, columnas=8) == [0.0] * 8


def test_una_senal_mas_corta_que_las_columnas_no_revienta(tmp_path):
    ruta = tmp_path / "corta.wav"
    sf.write(ruta, secuencia([(440.0, 0.002)], sr=16000), 16000)
    picos = forma_de_onda(ruta, columnas=100)
    assert len(picos) == 100


def test_la_forma_de_onda_falla_con_claridad_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(ErrorAudio):
        forma_de_onda(tmp_path / "no.wav")


def test_convertir_para_escucha_produce_un_m4a_con_la_misma_duracion(tmp_path):
    ruta = tmp_path / "origen.wav"
    sf.write(ruta, secuencia([(440.0, 1.5)], sr=44100), 44100)
    salida = convertir_para_escucha(ruta, tmp_path / "escucha" / "escucha.m4a")
    assert salida.exists() and salida.suffix == ".m4a"
    assert duracion_s(salida) == pytest.approx(1.5, abs=0.15)
