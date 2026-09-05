from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from transcripciones import trabajos
from transcripciones.models import Cancion, Fragmento


def _resultado_falso(**kwargs):
    nota = NotaContrato(orden=1, nombre="G4", midi=67, inicio_s=0.1, duracion_s=0.3,
                        confianza=0.9, cents=0)
    return Resultado(
        fragmento=FragmentoContrato(titulo="X", fuente="archivo", referencia="x.wav",
                                    inicio_s=30.0, fin_s=40.0),
        analisis=ParametrosAnalisis(separacion="ninguna", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cpu"),
        frases=(Frase(indice=1, inicio_s=0.1, fin_s=0.4, notas=(nota,)),),
        archivos={"midi": "media/x.mid"},
        avisos=(),
    )


class PruebaTrabajos(TestCase):
    def setUp(self):
        cancion = Cancion.objects.create(titulo="X", fuente="archivo", referencia="x.wav")
        self.fragmento = Fragmento.objects.create(
            cancion=cancion, origen="x.wav", inicio_s=30.0, fin_s=40.0, separar=False
        )

    def _preparado(self):
        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x/mezcla.wav"}
        self.fragmento.save()

    def test_la_preparacion_deja_el_fragmento_listo_para_escuchar(self):
        preparar = lambda **kwargs: (Path("media/x/mezcla.wav"), _resultado_falso().fragmento)
        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "x.wav")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PREPARADO
        assert self.fragmento.archivos["mezcla_wav"].endswith("mezcla.wav")

    def test_la_preparacion_pasa_la_cache_compartida_de_descargas(self):
        recibido = {}

        def preparar(**kwargs):
            recibido.update(kwargs)
            return Path("media/x/mezcla.wav"), _resultado_falso().fragmento

        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        assert recibido["cache_dir"] == trabajos.cache_descargas()
        assert str(self.fragmento.pk) not in str(recibido["cache_dir"])

    def test_la_preparacion_guarda_el_titulo_averiguado(self):
        preparar = lambda **kwargs: (Path("media/x/mezcla.wav"), _resultado_falso().fragmento)
        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        self.fragmento.refresh_from_db()
        assert self.fragmento.cancion.titulo == "X"

    def test_un_fallo_de_preparacion_deja_error_con_mensaje(self):
        def revienta(**kwargs):
            raise RuntimeError("no se pudo descargar el audio")

        with patch.object(trabajos, "_PREPARAR", revienta):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "no se pudo descargar" in self.fragmento.mensaje

    def test_el_analisis_deja_el_fragmento_listo(self):
        self._preparado()
        with patch.object(trabajos, "_ANALIZAR", lambda **kwargs: _resultado_falso()):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.notas.count() == 1

    def test_el_progreso_se_guarda_en_el_paso(self):
        self._preparado()
        pasos_vistos = []

        def analizar(**kwargs):
            kwargs["progreso"]("Separando la pista melódica")
            pasos_vistos.append(Fragmento.objects.get(pk=self.fragmento.pk).paso)
            return _resultado_falso()

        with patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert pasos_vistos == ["Separando la pista melódica"]

    def test_el_analisis_corre_con_el_semaforo_tomado(self):
        self._preparado()
        libres_durante = []

        def analizar(**kwargs):
            libres_durante.append(trabajos.UN_ANALISIS_A_LA_VEZ._value)
            return _resultado_falso()

        with patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert libres_durante == [0]                       # tomado mientras analiza
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1   # y devuelto al terminar

    def test_el_semaforo_se_devuelve_aunque_el_analisis_falle(self):
        self._preparado()

        def revienta(**kwargs):
            raise RuntimeError("CUDA out of memory")

        with patch.object(trabajos, "_ANALIZAR", revienta):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_recuperar_huerfanos_marca_error_los_trabajos_a_medias(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.paso = "Separando"
        self.fragmento.save()
        otro = Fragmento.objects.create(
            cancion=self.fragmento.cancion, origen="x.wav", inicio_s=0, fin_s=5,
            estado=Fragmento.LISTO,
        )
        assert trabajos.recuperar_huerfanos() == 1
        self.fragmento.refresh_from_db()
        otro.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "interrumpi" in self.fragmento.mensaje
        assert otro.estado == Fragmento.LISTO

    def test_el_comando_recuperar_trabajos_existe(self):
        self.fragmento.estado = Fragmento.PREPARANDO
        self.fragmento.save()
        call_command("recuperar_trabajos")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_el_directorio_de_trabajo_es_propio_de_cada_fragmento(self):
        ruta = trabajos.directorio_de(self.fragmento)
        assert str(self.fragmento.pk) in str(ruta)
