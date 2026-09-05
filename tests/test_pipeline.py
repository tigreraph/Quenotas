from pathlib import Path

import pytest
import soundfile as sf

from motor import pipeline
from motor.config import Config
from motor.contrato import Fragmento
from tests.senales import curva, secuencia


@pytest.fixture
def recorte(tmp_path):
    ruta = tmp_path / "recorte.wav"
    sf.write(ruta, secuencia([(440.0, 0.5), (None, 0.8), (493.88, 0.5)], sr=44100), 44100)
    return ruta


@pytest.fixture
def detector_falso(monkeypatch):
    """Sustituye CREPE por una curva conocida para no cargar el modelo."""
    def detectar(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69, 0.5), (None, 0.8), (71, 0.5)], hop_s=hop_ms / 1000)
        return f0, confianza, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar)


def _fragmento():
    return Fragmento(titulo="Ensayo", fuente="archivo", referencia="recorte.wav",
                     inicio_s=30.0, fin_s=31.8)


def test_analizar_devuelve_las_notas_en_frases(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert [frase.indice for frase in resultado.frases] == [1, 2]
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]


def test_los_tiempos_son_relativos_al_inicio_del_fragmento(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.notas[0].inicio_s == pytest.approx(0.0, abs=0.02)
    assert resultado.fragmento.inicio_s == 30.0


def test_registra_los_parametros_del_analisis(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.analisis.separacion == "ninguna"
    assert resultado.analisis.hop_ms == 10
    assert resultado.analisis.fmin_hz == pytest.approx(261.63)
    assert resultado.analisis.dispositivo in {"cpu", "cuda"}


def test_avisa_cuando_toda_la_confianza_es_baja(recorte, monkeypatch):
    def detectar_ruido(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69, 1.0)], hop_s=hop_ms / 1000)
        return f0, confianza * 0.0 + 0.2, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar_ruido)
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.frases == ()
    assert any("no se detectó" in aviso.lower() for aviso in resultado.avisos)


def test_registra_la_afinacion_del_instrumento_y_avisa_si_es_grande(recorte, monkeypatch):
    def detectar_desafinado(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69.4, 0.6), (71.4, 0.6)], hop_s=hop_ms / 1000)
        return f0, confianza, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar_desafinado)
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.analisis.afinacion_cents == pytest.approx(40, abs=3)
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert any("afinad" in aviso.lower() for aviso in resultado.avisos)


def test_rechaza_un_fragmento_mas_largo_que_el_limite(recorte, detector_falso):
    config = Config.desde_entorno({"SACANOTAS_MAX_FRAGMENTO_S": "1.0"})
    with pytest.raises(pipeline.ErrorPipeline) as error:
        pipeline.analizar_recorte(recorte, _fragmento(), config=config, separar=False)
    assert "180" in str(error.value) or "1.0" in str(error.value)


def test_informa_del_progreso(recorte, detector_falso):
    mensajes = []
    pipeline.analizar_recorte(recorte, _fragmento(), separar=False, progreso=mensajes.append)
    assert any("afinación" in mensaje for mensaje in mensajes)


def test_genera_los_archivos_cuando_se_le_da_un_directorio(recorte, detector_falso, tmp_path):
    salidas = tmp_path / "salidas"
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=salidas
    )
    assert set(resultado.archivos) >= {"mezcla_wav", "notas_wav", "midi", "txt", "pdf"}
    for clave, ruta in resultado.archivos.items():
        assert Path(ruta).exists(), f"falta el archivo de {clave}"


def test_sin_directorio_de_salida_no_genera_archivos(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.archivos == {}


def test_un_exportador_que_falla_deja_aviso_y_no_tumba_el_analisis(
    recorte, detector_falso, tmp_path, monkeypatch
):
    def revienta(resultado, ruta):
        raise RuntimeError("fuente no encontrada")

    monkeypatch.setattr(pipeline, "a_pdf", revienta)
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=tmp_path / "salidas"
    )
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert "pdf" not in resultado.archivos
    assert "midi" in resultado.archivos
    assert any("PDF" in aviso for aviso in resultado.avisos)
