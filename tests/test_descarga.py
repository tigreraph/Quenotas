import subprocess
import types

import pytest

from motor import descarga


def _respuesta(stdout="", stderr="", codigo=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=codigo)


def test_reconoce_una_url():
    assert descarga.es_url("https://www.youtube.com/watch?v=abc")
    assert descarga.es_url("http://youtu.be/abc")
    assert not descarga.es_url("C:/audios/ensayo.wav")
    assert not descarga.es_url("ensayo.wav")


def test_obtener_info_devuelve_id_y_titulo_en_una_llamada(monkeypatch):
    llamadas = []

    def simular(comando):
        llamadas.append(comando)
        return _respuesta(stdout="abc123\nHuayno de prueba\n")

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    assert descarga.obtener_info("https://youtu.be/abc123") == ("abc123", "Huayno de prueba")
    assert len(llamadas) == 1


def test_obtener_info_no_revienta_si_falla(monkeypatch):
    def falla(comando):
        raise subprocess.CalledProcessError(1, comando, stderr="Video unavailable")

    monkeypatch.setattr(descarga, "_EJECUTAR", falla)
    assert descarga.obtener_info("https://youtu.be/abc") == ("", "")


def test_descargar_guarda_por_id_en_formato_nativo(monkeypatch, tmp_path):
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        (tmp_path / "abc123.m4a").write_bytes(b"fingido")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"
    assert "-x" not in capturado["comando"]          # sin convertir a WAV


def test_descargar_reutiliza_el_archivo_en_cache(monkeypatch, tmp_path):
    (tmp_path / "abc123.m4a").write_bytes(b"ya estaba")

    def no_debia_llamarse(comando):
        raise AssertionError("no debía tocar la red: el archivo ya estaba en caché")

    monkeypatch.setattr(descarga, "_EJECUTAR", no_debia_llamarse)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"


def test_una_descarga_a_medias_no_cuenta_como_cache(monkeypatch, tmp_path):
    (tmp_path / "abc123.m4a.part").write_bytes(b"incompleto")

    def simular(comando):
        (tmp_path / "abc123.m4a").write_bytes(b"completo")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"


def test_descargar_averigua_el_id_si_no_se_lo_dan(monkeypatch, tmp_path):
    def simular(comando):
        if "--skip-download" in comando:
            return _respuesta(stdout="abc123\nHuayno\n")
        (tmp_path / "abc123.webm").write_bytes(b"fingido")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path)
    assert ruta.name == "abc123.webm"


def test_descargar_avisa_con_claridad_si_youtube_bloquea(monkeypatch, tmp_path):
    def bloqueado(comando):
        raise subprocess.CalledProcessError(
            1, comando, stderr="ERROR: Sign in to confirm you are not a bot"
        )

    monkeypatch.setattr(descarga, "_EJECUTAR", bloqueado)
    with pytest.raises(descarga.ErrorDescarga) as error:
        descarga.descargar_audio("https://youtu.be/abc", tmp_path, id_video="abc")
    mensaje = str(error.value)
    assert "no se pudo descargar" in mensaje.lower()
    assert "sube el archivo" in mensaje.lower()


def test_descargar_avisa_si_no_aparece_el_archivo(monkeypatch, tmp_path):
    monkeypatch.setattr(descarga, "_EJECUTAR", lambda comando: _respuesta())
    with pytest.raises(descarga.ErrorDescarga):
        descarga.descargar_audio("https://youtu.be/abc", tmp_path, id_video="abc")
