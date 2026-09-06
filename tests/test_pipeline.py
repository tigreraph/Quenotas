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


def test_si_no_se_puede_crear_la_carpeta_de_salida_se_avisa_y_se_conservan_las_notas(
    recorte, detector_falso
):
    # Una carpeta "dentro" de un archivo no se puede crear: mkdir lanza OSError.
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=recorte / "salidas"
    )
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert set(resultado.archivos) == {"mezcla_wav"}
    assert any("carpeta" in aviso.lower() for aviso in resultado.avisos)


import soundfile as sf

from motor import descarga as modulo_descarga
from motor import separacion as modulo_separacion


@pytest.fixture
def cancion_larga(tmp_path):
    ruta = tmp_path / "cancion.wav"
    sf.write(ruta, secuencia([(440.0, 5.0)], sr=44100), 44100)
    return ruta


def test_analizar_fuente_desde_archivo_sin_separar(cancion_larga, detector_falso, tmp_path):
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=False, titulo="Ensayo",
    )
    assert resultado.fragmento.fuente == "archivo"
    assert resultado.fragmento.inicio_s == 1.0
    assert resultado.analisis.separacion == "ninguna"
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert Path(resultado.archivos["midi"]).exists()


def _descarga_falsa(cancion_larga):
    """Imita a descargar_audio: deja la canción en la caché y devuelve la ruta."""
    def descargar(url, cache_dir, id_video=""):
        destino = Path(cache_dir) / f"{id_video or 'abc'}.m4a"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(cancion_larga.read_bytes())
        return destino
    return descargar


def _separacion_falsa(ruta_wav, directorio_salida, dispositivo="cpu",
                      modelo="htdemucs", segmento=None):
    destino = Path(directorio_salida) / "other.wav"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(Path(ruta_wav).read_bytes())
    return destino


def test_analizar_fuente_desde_url_descarga_y_separa(monkeypatch, cancion_larga,
                                                     detector_falso, tmp_path):
    monkeypatch.setattr(modulo_descarga, "descargar_audio", _descarga_falsa(cancion_larga))
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    monkeypatch.setattr(modulo_separacion, "separar_melodia", _separacion_falsa)

    resultado = pipeline.analizar_fuente(
        "https://youtu.be/abc", inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
        cache_dir=tmp_path / "origen",
    )
    assert resultado.fragmento.fuente == "youtube"
    assert resultado.fragmento.titulo == "Huayno"
    assert resultado.analisis.separacion == "htdemucs"
    assert Path(resultado.archivos["melodia_wav"]).exists()
    assert (tmp_path / "origen" / "abc.m4a").exists()      # la descarga queda en la caché


def test_dos_fragmentos_de_la_misma_url_comparten_la_descarga(monkeypatch, cancion_larga,
                                                              detector_falso, tmp_path):
    descargas = []

    def descargar(url, cache_dir, id_video=""):
        descargas.append(id_video)
        return _descarga_falsa(cancion_larga)(url, cache_dir, id_video)

    monkeypatch.setattr(modulo_descarga, "descargar_audio", descargar)
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    for indice, (inicio, fin) in enumerate([(0.5, 2.0), (2.0, 3.5)]):
        pipeline.preparar(
            "https://youtu.be/abc", inicio, fin, tmp_path / f"trabajo{indice}",
            cache_dir=tmp_path / "origen",
        )
    # preparar pasa el id averiguado, así que descargar_audio puede encontrar
    # la caché sin volver a preguntar; y usa siempre la misma carpeta.
    assert descargas == ["abc", "abc"]


def test_sin_memoria_de_video_la_separacion_reintenta_en_cpu(monkeypatch, cancion_larga,
                                                             detector_falso, tmp_path):
    dispositivos = []

    def separar(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None):
        dispositivos.append(dispositivo)
        if dispositivo == "cuda":
            raise modulo_separacion.ErrorSeparacion("La separación falló: CUDA out of memory")
        return _separacion_falsa(ruta_wav, directorio_salida, dispositivo, modelo)

    monkeypatch.setattr(modulo_separacion, "separar_melodia", separar)
    monkeypatch.setattr(pipeline, "resolver_dispositivo", lambda preferencia: "cuda")
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
    )
    assert dispositivos == ["cuda", "cpu"]
    assert resultado.analisis.separacion == "htdemucs"
    assert any("cpu" in aviso.lower() for aviso in resultado.avisos)


def test_si_tambien_falla_en_cpu_no_se_avisa_que_corrio_en_cpu(monkeypatch, cancion_larga,
                                                                detector_falso, tmp_path):
    def separar(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None):
        if dispositivo == "cuda":
            raise modulo_separacion.ErrorSeparacion("La separación falló: CUDA out of memory")
        raise modulo_separacion.ErrorSeparacion("modelo corrupto")

    monkeypatch.setattr(modulo_separacion, "separar_melodia", separar)
    monkeypatch.setattr(pipeline, "resolver_dispositivo", lambda preferencia: "cuda")
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
    )
    assert resultado.analisis.separacion == "ninguna"
    assert not any("corrió en cpu" in aviso.lower() for aviso in resultado.avisos)
    assert any("separación falló" in aviso.lower() for aviso in resultado.avisos)


def test_si_la_separacion_falla_sigue_con_la_mezcla_y_avisa(monkeypatch, cancion_larga,
                                                            detector_falso, tmp_path):
    def revienta(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None):
        raise modulo_separacion.ErrorSeparacion("modelo corrupto")

    monkeypatch.setattr(modulo_separacion, "separar_melodia", revienta)
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
    )
    assert resultado.analisis.separacion == "ninguna"
    assert any("separación" in aviso.lower() for aviso in resultado.avisos)


from motor.pipeline import Fuente, obtener_audio


def test_obtener_audio_de_un_archivo_local(cancion_larga):
    fuente = obtener_audio(cancion_larga)
    assert isinstance(fuente, Fuente)
    assert fuente.ruta == cancion_larga
    assert fuente.fuente == "archivo"
    assert fuente.referencia == "cancion.wav"
    assert fuente.titulo == "cancion"


def test_obtener_audio_de_una_url_descarga_a_la_cache(monkeypatch, cancion_larga, tmp_path):
    monkeypatch.setattr(modulo_descarga, "descargar_audio", _descarga_falsa(cancion_larga))
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    fuente = obtener_audio("https://youtu.be/abc", cache_dir=tmp_path / "origen")
    assert fuente.fuente == "youtube"
    assert fuente.titulo == "Huayno"
    assert fuente.referencia == "https://youtu.be/abc"
    assert fuente.ruta == tmp_path / "origen" / "abc.m4a"


def test_obtener_audio_avisa_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(pipeline.ErrorPipeline) as error:
        obtener_audio(tmp_path / "no_existe.wav")
    assert "no existe" in str(error.value)
