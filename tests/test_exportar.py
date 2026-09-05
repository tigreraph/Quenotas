import pretty_midi
import pytest

from motor.contrato import Fragmento, Frase, Nota, ParametrosAnalisis, Resultado
from motor.exportar import a_midi, a_txt


def _resultado():
    notas_frase_uno = (
        Nota(orden=1, nombre="G4", midi=67, inicio_s=0.4, duracion_s=0.42,
             confianza=0.93, cents=-12),
        Nota(orden=2, nombre="A4", midi=69, inicio_s=0.9, duracion_s=0.21,
             confianza=0.71, cents=4),
    )
    notas_frase_dos = (
        Nota(orden=3, nombre="B4", midi=71, inicio_s=2.0, duracion_s=0.6,
             confianza=0.40, cents=30),
    )
    return Resultado(
        fragmento=Fragmento(titulo="Huayno de prueba", fuente="youtube",
                            referencia="https://ejemplo/abc", inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="htdemucs", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cuda"),
        frases=(
            Frase(indice=1, inicio_s=0.4, fin_s=1.11, notas=notas_frase_uno),
            Frase(indice=2, inicio_s=2.0, fin_s=2.6, notas=notas_frase_dos),
        ),
        archivos={},
        avisos=("La confianza media es baja.",),
    )


def test_el_midi_conserva_alturas_y_tiempos(tmp_path):
    ruta = a_midi(_resultado().frases, tmp_path / "melodia.mid")
    leido = pretty_midi.PrettyMIDI(str(ruta))
    assert len(leido.instruments) == 1
    assert leido.instruments[0].program == 73
    alturas = [nota.pitch for nota in leido.instruments[0].notes]
    assert alturas == [67, 69, 71]
    primera = leido.instruments[0].notes[0]
    assert primera.start == pytest.approx(0.4, abs=0.01)
    assert primera.end == pytest.approx(0.82, abs=0.01)


def test_el_midi_sin_notas_se_genera_igual(tmp_path):
    ruta = a_midi((), tmp_path / "vacio.mid")
    assert ruta.exists()
    # pretty_midi solo crea instrumentos al encontrar notas: al releer un
    # archivo vacío, instruments queda [] (verificado con 0.2.11.post0).
    leido = pretty_midi.PrettyMIDI(str(ruta))
    assert sum(len(instrumento.notes) for instrumento in leido.instruments) == 0


def test_el_txt_muestra_tiempos_absolutos_y_agrupa_por_frases(tmp_path):
    ruta = a_txt(_resultado(), tmp_path / "notas.txt")
    texto = ruta.read_text(encoding="utf-8")
    assert "Huayno de prueba" in texto
    assert "Frase 1" in texto and "Frase 2" in texto
    assert "0:30.4" in texto          # 30.0 del fragmento + 0.4 de la nota
    assert "G4" in texto and "B4" in texto
    assert "alta" in texto and "baja" in texto
    assert "La confianza media es baja." in texto


def test_el_txt_indica_cuando_no_hay_notas(tmp_path):
    vacio = Resultado(
        fragmento=_resultado().fragmento,
        analisis=_resultado().analisis,
        frases=(),
        archivos={},
        avisos=(),
    )
    texto = a_txt(vacio, tmp_path / "vacio.txt").read_text(encoding="utf-8")
    assert "No se detectaron notas" in texto
