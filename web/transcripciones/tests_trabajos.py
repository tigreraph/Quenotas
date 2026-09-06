from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from motor.pipeline import Fuente
from transcripciones import trabajos
from transcripciones.models import Cancion, Fragmento


def _resultado_falso():
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


def _fuente_falsa(**kwargs):
    return Fuente(ruta=Path("media/origen/abc.m4a"), titulo="Huayno", fuente="youtube",
                  referencia="https://youtu.be/abc")


def _escucha_falsa(ruta_original, directorio):
    return Path(directorio) / "escucha.m4a", 42.5


class PruebaTrabajos(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="X", fuente="archivo", referencia="x.wav", origen="media/subidas/x.wav",
            audio_original="media/subidas/x.wav", estado=Cancion.LISTA, duracion_s=120.0,
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, inicio_s=30.0, fin_s=40.0, separar=False,
        )

    # --- preparación de la canción ---

    def test_la_preparacion_deja_la_cancion_lista_con_audio_y_duracion(self):
        cancion = Cancion.objects.create(titulo="", fuente="youtube",
                                         referencia="https://youtu.be/abc", origen="https://youtu.be/abc")
        with patch.object(trabajos, "_OBTENER", _fuente_falsa), \
             patch.object(trabajos, "_PREPARAR_ESCUCHA", _escucha_falsa):
            trabajos.ejecutar_preparacion_cancion(cancion.pk)
        cancion.refresh_from_db()
        assert cancion.estado == Cancion.LISTA
        assert cancion.titulo == "Huayno"
        assert cancion.audio_original.endswith("abc.m4a")
        assert cancion.audio_escucha.endswith("escucha.m4a")
        assert cancion.duracion_s == 42.5
        assert cancion.paso == ""

    def test_la_preparacion_de_la_cancion_corre_fuera_del_semaforo(self):
        valores = []

        def obtener(origen, **kwargs):
            valores.append(trabajos.UN_ANALISIS_A_LA_VEZ._value)
            return _fuente_falsa()

        with patch.object(trabajos, "_OBTENER", obtener), \
             patch.object(trabajos, "_PREPARAR_ESCUCHA", _escucha_falsa):
            trabajos.ejecutar_preparacion_cancion(self.cancion.pk)
        assert valores == [1]

    def test_la_preparacion_usa_la_cache_compartida_y_la_carpeta_de_la_cancion(self):
        recibido = {}

        def obtener(origen, **kwargs):
            recibido.update(kwargs)
            return _fuente_falsa()

        carpetas = []

        def escucha(ruta_original, directorio):
            carpetas.append(Path(directorio))
            return Path(directorio) / "escucha.m4a", 1.0

        with patch.object(trabajos, "_OBTENER", obtener), patch.object(trabajos, "_PREPARAR_ESCUCHA", escucha):
            trabajos.ejecutar_preparacion_cancion(self.cancion.pk)
        assert recibido["cache_dir"] == trabajos.cache_descargas()
        assert carpetas == [trabajos.directorio_cancion(self.cancion)]
        assert str(self.cancion.pk) in str(carpetas[0])

    def test_un_fallo_de_preparacion_deja_la_cancion_en_error_con_mensaje(self):
        def revienta(origen, **kwargs):
            raise RuntimeError("No se pudo descargar el audio del enlace")

        with patch.object(trabajos, "_OBTENER", revienta):
            trabajos.ejecutar_preparacion_cancion(self.cancion.pk)
        self.cancion.refresh_from_db()
        assert self.cancion.estado == Cancion.ERROR
        assert "No se pudo descargar" in self.cancion.mensaje

    # --- frases ---

    def test_ejecutar_frase_recorta_desde_el_audio_de_la_cancion_y_deja_listo(self):
        recortes = []

        def recortar(entrada, salida, inicio_s, fin_s):
            recortes.append((str(entrada), inicio_s, fin_s))
            return Path(salida)

        with patch.object(trabajos, "_RECORTAR", recortar), \
             patch.object(trabajos, "_ANALIZAR", lambda **kwargs: _resultado_falso()):
            trabajos.ejecutar_frase(self.fragmento.pk)
        self.fragmento.refresh_from_db()
        assert recortes == [("media/subidas/x.wav", 30.0, 40.0)]
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.notas.count() == 1

    def test_el_analisis_recibe_el_recorte_y_el_fragmento_del_contrato(self):
        recibido = {}

        def analizar(**kwargs):
            recibido.update(kwargs)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert str(recibido["recorte"]).endswith("mezcla.wav")
        assert recibido["fragmento"].inicio_s == 30.0
        assert recibido["fragmento"].titulo == "X"
        assert recibido["separar"] is False

    def test_el_progreso_se_guarda_en_el_paso(self):
        pasos_vistos = []

        def analizar(**kwargs):
            kwargs["progreso"]("Separando la pista melódica")
            pasos_vistos.append(Fragmento.objects.get(pk=self.fragmento.pk).paso)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert pasos_vistos == ["Separando la pista melódica"]

    def test_la_frase_corre_con_el_semaforo_tomado_y_lo_devuelve(self):
        libres_durante = []

        def analizar(**kwargs):
            libres_durante.append(trabajos.UN_ANALISIS_A_LA_VEZ._value)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert libres_durante == [0]
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1

    def test_el_semaforo_se_devuelve_y_queda_error_si_el_recorte_falla(self):
        def revienta(entrada, salida, inicio_s, fin_s):
            raise RuntimeError("el rango pedido llega hasta 40.0 s pero la duración del audio es de 35.0 s")

        with patch.object(trabajos, "_RECORTAR", revienta):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "duración del audio" in self.fragmento.mensaje

    # --- recuperación ---

    def test_recuperar_huerfanos_cubre_canciones_y_frases(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.save()
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.save()
        otra = Cancion.objects.create(titulo="Y", estado=Cancion.LISTA)
        assert trabajos.recuperar_huerfanos() == 2
        self.cancion.refresh_from_db()
        self.fragmento.refresh_from_db()
        otra.refresh_from_db()
        assert self.cancion.estado == Cancion.ERROR
        assert "interrumpi" in self.cancion.mensaje
        assert self.fragmento.estado == Fragmento.ERROR
        assert otra.estado == Cancion.LISTA

    def test_el_comando_recuperar_trabajos_existe(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.save()
        call_command("recuperar_trabajos")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_los_directorios_son_propios_de_cada_objeto(self):
        assert str(self.fragmento.pk) in str(trabajos.directorio_de(self.fragmento))
        assert "canciones" in str(trabajos.directorio_cancion(self.cancion))
        assert str(self.cancion.pk) in str(trabajos.directorio_cancion(self.cancion))
