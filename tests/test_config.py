from pathlib import Path

from motor.config import Config, resolver_dispositivo


def test_valores_por_defecto_son_los_de_la_quena_en_sol():
    config = Config.desde_entorno({})
    assert config.fmin_hz == 261.63
    assert config.fmax_hz == 1567.98
    assert config.hop_ms == 10
    assert config.umbral_confianza == 0.5
    assert config.ventana_mediana == 5
    assert config.max_fragmento_s == 180.0
    assert config.segmento_demucs == 6.0
    assert config.modelo_separacion == "htdemucs_6s"


def test_el_entorno_sobrescribe_los_valores():
    config = Config.desde_entorno({
        "SACANOTAS_FMIN_HZ": "130.81",
        "SACANOTAS_MEDIA": "D:/tmp/media",
        "SACANOTAS_UMBRAL_CONFIANZA": "0.7",
    })
    assert config.fmin_hz == 130.81
    assert config.umbral_confianza == 0.7
    assert config.media_dir == Path("D:/tmp/media")


def test_la_ventana_de_mediana_debe_ser_impar():
    try:
        Config.desde_entorno({"SACANOTAS_VENTANA_MEDIANA": "4"})
    except ValueError as error:
        assert "impar" in str(error)
    else:
        raise AssertionError("debía rechazar una ventana par")


def test_resolver_dispositivo_respeta_lo_pedido():
    assert resolver_dispositivo("cpu") == "cpu"
    assert resolver_dispositivo("auto") in {"cpu", "cuda"}
