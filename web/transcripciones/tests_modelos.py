import importlib

from django.apps import apps
from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from transcripciones.models import Cancion, Fragmento, Nota


def _resultado():
    notas = (
        NotaContrato(orden=1, nombre="G4", midi=67, inicio_s=0.4, duracion_s=0.42,
                     confianza=0.93, cents=-12),
        NotaContrato(orden=2, nombre="A4", midi=69, inicio_s=1.5, duracion_s=0.30,
                     confianza=0.55, cents=3),
    )
    return Resultado(
        fragmento=FragmentoContrato(titulo="Huayno", fuente="youtube",
                                    referencia="https://youtu.be/abc",
                                    inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="htdemucs", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cuda"),
        frases=(
            Frase(indice=1, inicio_s=0.4, fin_s=0.82, notas=(notas[0],)),
            Frase(indice=2, inicio_s=1.5, fin_s=1.8, notas=(notas[1],)),
        ),
        archivos={"midi": "media/x.mid"},
        avisos=("un aviso",),
    )


class PruebaModelos(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="Huayno", fuente="youtube", referencia="https://youtu.be/abc"
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, inicio_s=30.0, fin_s=90.0, separar=True
        )

    def test_un_fragmento_nace_pendiente(self):
        assert self.fragmento.estado == Fragmento.PENDIENTE

    def test_guardar_resultado_crea_las_notas_con_su_frase(self):
        self.fragmento.guardar_resultado(_resultado())
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.avisos == ["un aviso"]
        assert self.fragmento.archivos["midi"] == "media/x.mid"
        assert list(self.fragmento.notas.values_list("nombre", "frase")) == [
            ("G4", 1), ("A4", 2)
        ]

    def test_guardar_resultado_dos_veces_no_duplica_notas(self):
        self.fragmento.guardar_resultado(_resultado())
        self.fragmento.guardar_resultado(_resultado())
        assert self.fragmento.notas.count() == 2

    def test_etiqueta_de_confianza(self):
        self.fragmento.guardar_resultado(_resultado())
        etiquetas = [nota.etiqueta_confianza for nota in self.fragmento.notas.all()]
        assert etiquetas == ["alta", "baja"]

    def test_agrupar_por_frases_devuelve_listas(self):
        self.fragmento.guardar_resultado(_resultado())
        frases = self.fragmento.por_frases()
        assert [indice for indice, _ in frases] == [1, 2]
        assert [nota.nombre for nota in frases[0][1]] == ["G4"]

    def test_una_cancion_nace_pendiente_y_sin_audio(self):
        assert self.cancion.estado == Cancion.PENDIENTE
        assert self.cancion.lista is False
        assert self.cancion.duracion_s is None
        assert self.cancion.separar is True

    def test_las_frases_de_la_cancion_van_por_tiempo_no_por_fecha(self):
        Fragmento.objects.create(cancion=self.cancion, inicio_s=90.0, fin_s=120.0)
        Fragmento.objects.create(cancion=self.cancion, inicio_s=10.0, fin_s=20.0)
        assert [f.inicio_s for f in self.cancion.frases()] == [10.0, 30.0, 90.0]

    def test_la_migracion_0003_rellena_el_origen_de_las_canciones_viejas(self):
        modulo = importlib.import_module("transcripciones.migrations.0003_rellenar_origen")
        cancion_youtube = Cancion.objects.create(
            titulo="Vieja", fuente="youtube", referencia="https://youtu.be/vieja", origen="",
        )
        cancion_archivo = Cancion.objects.create(
            titulo="Vieja archivo", fuente="archivo", referencia="no_existe.mp3", origen="",
        )
        modulo.rellenar_origen(apps, None)
        cancion_youtube.refresh_from_db()
        cancion_archivo.refresh_from_db()
        assert cancion_youtube.origen == cancion_youtube.referencia
        assert cancion_archivo.origen == ""
