import subprocess
import types

import pytest

from motor import separacion


def test_devuelve_la_pista_other(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    salida = tmp_path / "separado"

    def simular(comando):
        destino = salida / "htdemucs_6s" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"RIFF fingido")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    ruta = separacion.separar_melodia(entrada, salida, dispositivo="cpu")
    assert ruta.name == "other.wav"
    assert ruta.exists()


def test_pasa_el_dispositivo_y_el_modelo_al_comando(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        destino = tmp_path / "separado" / "htdemucs_6s" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"x")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    separacion.separar_melodia(entrada, tmp_path / "separado", dispositivo="cuda")
    assert "cuda" in capturado["comando"]
    assert "htdemucs_6s" in capturado["comando"]
    assert "--segment" not in capturado["comando"]


def test_pasa_el_segmento_cuando_se_indica(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        destino = tmp_path / "separado" / "htdemucs_6s" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"x")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    separacion.separar_melodia(entrada, tmp_path / "separado", dispositivo="cuda", segmento=6)
    posicion = capturado["comando"].index("--segment")
    assert capturado["comando"][posicion + 1] == "6"


def test_avisa_si_demucs_falla(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")

    def falla(comando):
        raise subprocess.CalledProcessError(1, comando, stderr="CUDA out of memory")

    monkeypatch.setattr(separacion, "_EJECUTAR", falla)
    with pytest.raises(separacion.ErrorSeparacion) as error:
        separacion.separar_melodia(entrada, tmp_path / "separado")
    assert "CUDA out of memory" in str(error.value)


def test_avisa_si_no_aparece_la_pista(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    monkeypatch.setattr(
        separacion, "_EJECUTAR",
        lambda comando: types.SimpleNamespace(stdout="", stderr="", returncode=0),
    )
    with pytest.raises(separacion.ErrorSeparacion):
        separacion.separar_melodia(entrada, tmp_path / "separado")
