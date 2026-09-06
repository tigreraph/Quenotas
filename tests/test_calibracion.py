"""La prueba que decide si el sistema merece confianza.

Se apoya en una grabación real de la quena tocando una escala conocida.
Mientras esta prueba no pase, no hay razón para creerle el resultado de
una canción.
"""
from pathlib import Path

import pytest

from motor.config import Config
from motor.contrato import Fragmento
from motor.pipeline import analizar_recorte

FIJO = Path(__file__).parent / "fijos" / "escala_quena.wav"
ESPERADO = ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]


@pytest.mark.lento
@pytest.mark.skipif(not FIJO.exists(), reason="falta la grabación de calibración")
def test_la_escala_de_sol_se_reconoce_completa():
    resultado = analizar_recorte(
        FIJO,
        Fragmento(titulo="Calibración", fuente="archivo", referencia=FIJO.name,
                  inicio_s=0.0, fin_s=10.0),
        config=Config.desde_entorno({"QUENOTAS_DISPOSITIVO": "cpu"}),
        separar=False,
    )
    detectadas = [nota.nombre for nota in resultado.notas]
    assert detectadas == ESPERADO, f"se esperaba {ESPERADO} y salió {detectadas}"


@pytest.mark.lento
@pytest.mark.skipif(not FIJO.exists(), reason="falta la grabación de calibración")
def test_la_afinacion_de_la_quena_no_se_desvia_demasiado():
    resultado = analizar_recorte(
        FIJO,
        Fragmento(titulo="Calibración", fuente="archivo", referencia=FIJO.name,
                  inicio_s=0.0, fin_s=10.0),
        config=Config.desde_entorno({"QUENOTAS_DISPOSITIVO": "cpu"}),
        separar=False,
    )
    desviaciones = [abs(nota.cents) for nota in resultado.notas]
    assert max(desviaciones) < 40, f"desviaciones en cents: {desviaciones}"
