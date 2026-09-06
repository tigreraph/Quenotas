import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from transcripciones.formularios import parsear_tiempo
from transcripciones.models import Cancion, Fragmento, Nota


def test_parsear_tiempo_acepta_los_tres_formatos():
    assert parsear_tiempo("90") == 90.0
    assert parsear_tiempo("1:30") == 90.0
    assert parsear_tiempo("1:30.5") == 90.5
    assert parsear_tiempo("0:07") == 7.0


def test_parsear_tiempo_rechaza_basura():
    for texto in ["", "abc", "1:2:3", "-5", "1:75"]:
        with pytest.raises(ValueError):
            parsear_tiempo(texto)


# MEDIA_ROOT temporal para toda la clase: las vistas de onda y escucha miran el
# disco, y con el media/ real un archivo dejado por una prueba manual haría
# pasar o fallar tests según lo que haya en la carpeta.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="sacanotas-tests-"))
class PruebaVistas(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="Huayno", fuente="youtube", referencia="https://youtu.be/abc",
            origen="https://youtu.be/abc", audio_original="media/origen/abc.m4a",
            audio_escucha="media/canciones/no-existe/escucha.m4a", duracion_s=200.0,
            estado=Cancion.LISTA,
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, origen="https://youtu.be/abc",
            inicio_s=30.0, fin_s=90.0, separar=True,
        )

    # --- inicio ---

    def test_el_index_responde_y_ya_no_pide_tiempos(self):
        respuesta = self.client.get(reverse("index"))
        assert respuesta.status_code == 200
        assert b"YouTube" in respuesta.content
        assert b'name="inicio"' not in respuesta.content

    def test_enviar_una_url_crea_la_cancion_y_lanza_su_preparacion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("index"), {"url": "https://youtu.be/xyz"})
        creada = Cancion.objects.get(referencia="https://youtu.be/xyz")
        assert respuesta.status_code == 302
        assert respuesta["Location"] == reverse("cancion", args=[creada.pk])
        assert creada.origen == "https://youtu.be/xyz"
        assert creada.estado == Cancion.PREPARANDO
        lanzar.assert_called_once_with(creada.pk)

    def test_la_misma_url_reutiliza_la_cancion_y_no_la_vuelve_a_preparar(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("index"), {"url": "https://youtu.be/abc"})
        assert Cancion.objects.filter(referencia="https://youtu.be/abc").count() == 1
        assert respuesta["Location"] == reverse("cancion", args=[self.cancion.pk])
        lanzar.assert_not_called()

    def test_una_cancion_en_error_se_vuelve_a_preparar_al_enviar_su_url(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            self.client.post(reverse("index"), {"url": "https://youtu.be/abc"})
        lanzar.assert_called_once_with(self.cancion.pk)

    def test_reutilizar_una_cancion_sin_origen_lo_rellena_con_la_url(self):
        vieja = Cancion.objects.create(
            titulo="Vieja", fuente="youtube", referencia="https://youtu.be/vieja",
            origen="", estado=Cancion.ERROR,
        )
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            self.client.post(reverse("index"), {"url": "https://youtu.be/vieja"})
        vieja.refresh_from_db()
        assert vieja.origen == "https://youtu.be/vieja"
        lanzar.assert_called_once_with(vieja.pk)

    def test_subir_un_archivo_crea_la_cancion_con_su_ruta(self):
        with tempfile.TemporaryDirectory() as carpeta, override_settings(MEDIA_ROOT=carpeta):
            archivo = SimpleUploadedFile("ensayo.mp3", b"ID3fingido", content_type="audio/mpeg")
            with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
                self.client.post(reverse("index"), {"archivo": archivo})
            creada = Cancion.objects.get(fuente="archivo")
            assert creada.titulo == "ensayo"
            assert creada.origen.endswith("ensayo.mp3")
            assert Path(creada.origen).exists()
            lanzar.assert_called_once_with(creada.pk)

    def test_enviar_vacio_muestra_el_error(self):
        respuesta = self.client.post(reverse("index"), {})
        assert respuesta.status_code == 200
        assert "Pega un enlace".encode() in respuesta.content
        assert Cancion.objects.count() == 1

    # --- canción ---

    def test_la_cancion_lista_muestra_el_selector(self):
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert respuesta.status_code == 200
        assert b'id="onda"' in respuesta.content
        assert "Analizar esta selección".encode() in respuesta.content
        assert reverse("cancion_onda", args=[self.cancion.pk]).encode() in respuesta.content

    def test_la_cancion_en_preparacion_muestra_el_paso(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.paso = "Descargando el audio"
        self.cancion.save()
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert "Descargando el audio".encode() in respuesta.content
        assert b'id="onda"' not in respuesta.content

    def test_la_cancion_en_error_ofrece_reintentar(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.mensaje = "No se pudo descargar el audio del enlace"
        self.cancion.save()
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert "No se pudo descargar".encode() in respuesta.content
        assert reverse("cancion_reintentar", args=[self.cancion.pk]).encode() in respuesta.content

    def test_el_estado_de_la_cancion_trae_sus_frases_en_orden(self):
        Fragmento.objects.create(cancion=self.cancion, inicio_s=5.0, fin_s=15.0,
                                 estado=Fragmento.LISTO)
        datos = self.client.get(reverse("cancion_estado", args=[self.cancion.pk])).json()
        assert datos["estado"] == "lista"
        assert datos["duracion_s"] == 200.0
        assert datos["max_fragmento_s"] == 180.0
        assert datos["separar"] is True
        assert [f["inicio_s"] for f in datos["frases"]] == [5.0, 30.0]
        assert datos["frases"][0]["estado"] == "listo"
        assert datos["frases"][0]["url"] == reverse("detalle", args=[datos["frases"][0]["id"]])
        assert datos["frases"][0]["reintentar"] == reverse("reintentar", args=[datos["frases"][0]["id"]])

    def test_abrir_una_cancion_pendiente_con_origen_la_prepara(self):
        vieja = Cancion.objects.create(
            titulo="Vieja", fuente="youtube", referencia="https://youtu.be/vieja",
            origen="https://youtu.be/vieja", estado=Cancion.PENDIENTE,
        )
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.get(reverse("cancion", args=[vieja.pk]))
        lanzar.assert_called_once_with(vieja.pk)
        assert "Preparando".encode() in respuesta.content

    def test_abrir_una_cancion_pendiente_sin_origen_ofrece_reintentar(self):
        vieja = Cancion.objects.create(
            titulo="Vieja", fuente="youtube", referencia="https://youtu.be/vieja",
            origen="", estado=Cancion.PENDIENTE,
        )
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.get(reverse("cancion", args=[vieja.pk]))
        lanzar.assert_not_called()
        assert reverse("cancion_reintentar", args=[vieja.pk]).encode() in respuesta.content

    def test_reintentar_una_cancion_pendiente_la_prepara(self):
        vieja = Cancion.objects.create(
            titulo="Vieja", fuente="youtube", referencia="https://youtu.be/vieja",
            origen="https://youtu.be/vieja", estado=Cancion.PENDIENTE,
        )
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            self.client.post(reverse("cancion_reintentar", args=[vieja.pk]))
        lanzar.assert_called_once_with(vieja.pk)
        vieja.refresh_from_db()
        assert vieja.estado == Cancion.PREPARANDO

    def test_la_onda_da_404_si_todavia_no_existe(self):
        respuesta = self.client.get(reverse("cancion_onda", args=[self.cancion.pk]))
        assert respuesta.status_code == 404

    def test_la_onda_devuelve_los_picos_guardados(self):
        with tempfile.TemporaryDirectory() as carpeta, override_settings(MEDIA_ROOT=carpeta):
            directorio = Path(carpeta) / "canciones" / str(self.cancion.pk)
            directorio.mkdir(parents=True)
            (directorio / "onda.json").write_text(json.dumps([0.0, 0.5, 1.0]), encoding="utf-8")
            datos = self.client.get(reverse("cancion_onda", args=[self.cancion.pk])).json()
        assert datos["picos"] == [0.0, 0.5, 1.0]
        assert datos["duracion_s"] == 200.0

    def test_la_escucha_sirve_el_m4a_con_range(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "escucha.m4a"
            ruta.write_bytes(b"0123456789")
            self.cancion.audio_escucha = str(ruta)
            self.cancion.save()
            respuesta = self.client.get(reverse("cancion_escucha", args=[self.cancion.pk]),
                                        HTTP_RANGE="bytes=0-3")
            assert respuesta.status_code == 206
            assert respuesta["Content-Range"] == "bytes 0-3/10"
            assert b"".join(respuesta.streaming_content) == b"0123"

    def test_la_escucha_da_404_si_no_hay_archivo(self):
        respuesta = self.client.get(reverse("cancion_escucha", args=[self.cancion.pk]))
        assert respuesta.status_code == 404

    # --- crear frases ---

    def _crear(self, **campos):
        return self.client.post(reverse("crear_frase", args=[self.cancion.pk]), campos)

    def test_crear_una_frase_valida_la_deja_en_cola_y_lanza_el_trabajo(self):
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self._crear(inicio_s="10.5", fin_s="25", separar="true")
        assert respuesta.status_code == 201
        datos = respuesta.json()
        frase = Fragmento.objects.get(pk=datos["id"])
        assert frase.inicio_s == 10.5 and frase.fin_s == 25.0
        assert frase.estado == Fragmento.PROCESANDO and frase.paso == "En cola"
        assert frase.separar is True
        assert frase.origen == "https://youtu.be/abc"
        assert datos["url"] == reverse("detalle", args=[frase.pk])
        lanzar.assert_called_once_with(frase.pk)

    def test_crear_una_frase_acepta_tiempos_en_m_ss_y_recuerda_la_casilla(self):
        with patch("transcripciones.views.trabajos.lanzar_frase"):
            respuesta = self._crear(inicio_s="1:00", fin_s="1:30", separar="false")
        assert respuesta.status_code == 201
        frase = Fragmento.objects.get(pk=respuesta.json()["id"])
        assert frase.inicio_s == 60.0 and frase.fin_s == 90.0
        assert frase.separar is False
        self.cancion.refresh_from_db()
        assert self.cancion.separar is False

    def test_una_seleccion_invertida_corta_larga_o_fuera_da_400(self):
        casos = [
            dict(inicio_s="50", fin_s="40"),      # invertida
            dict(inicio_s="10", fin_s="10.5"),    # menos de 1 s
            dict(inicio_s="0", fin_s="190"),      # más de 180 s
            dict(inicio_s="150", fin_s="210"),    # más allá de la duración (200)
            dict(inicio_s="abc", fin_s="10"),     # basura
            dict(inicio_s="-5", fin_s="10"),      # inicio negativo
        ]
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            for campos in casos:
                respuesta = self._crear(**campos)
                assert respuesta.status_code == 400, campos
                assert "error" in respuesta.json()
        lanzar.assert_not_called()
        assert Fragmento.objects.count() == 1

    def test_no_se_pueden_crear_frases_si_la_cancion_no_esta_lista(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self._crear(inicio_s="0", fin_s="10")
        assert respuesta.status_code == 409
        lanzar.assert_not_called()

    def test_crear_frase_solo_acepta_post(self):
        respuesta = self.client.get(reverse("crear_frase", args=[self.cancion.pk]))
        assert respuesta.status_code == 405

    # --- reintentos ---

    def test_reintentar_una_frase_en_error_la_relanza(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PROCESANDO

    def test_reintentar_no_hace_nada_si_la_frase_no_esta_en_error(self):
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_not_called()

    def test_reintentar_la_cancion_en_error_la_vuelve_a_preparar(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("cancion_reintentar", args=[self.cancion.pk]))
        lanzar.assert_called_once_with(self.cancion.pk)
        assert respuesta["Location"] == reverse("cancion", args=[self.cancion.pk])
        self.cancion.refresh_from_db()
        assert self.cancion.estado == Cancion.PREPARANDO

    # --- detalle y resultado ---

    def _dejar_listo(self):
        self.fragmento.estado = Fragmento.LISTO
        self.fragmento.archivos = {"midi": "media/x.mid", "txt": "media/x.txt"}
        self.fragmento.avisos = ["La confianza media es baja."]
        self.fragmento.save()
        Nota.objects.create(fragmento=self.fragmento, frase=1, orden=1, nombre="G4",
                            midi=67, inicio_s=0.4, duracion_s=0.42, confianza=0.93, cents=-12)
        Nota.objects.create(fragmento=self.fragmento, frase=2, orden=2, nombre="B4",
                            midi=71, inicio_s=2.0, duracion_s=0.60, confianza=0.40, cents=30)

    def test_el_detalle_en_proceso_muestra_el_paso_y_el_enlace_a_la_cancion(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.paso = "Separando la pista melódica"
        self.fragmento.save()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "Separando la pista".encode() in contenido
        assert reverse("cancion", args=[self.cancion.pk]).encode() in contenido
        assert b"Analizar</button>" not in contenido

    def test_el_detalle_muestra_el_mensaje_de_error_y_reintentar(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.mensaje = "CUDA out of memory"
        self.fragmento.save()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"CUDA out of memory" in contenido
        assert reverse("reintentar", args=[self.fragmento.pk]).encode() in contenido

    def test_el_resultado_muestra_las_notas_agrupadas_por_frase(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Frase 1" in contenido and b"Frase 2" in contenido
        assert b"G4" in contenido and b"B4" in contenido
        assert "alta".encode() in contenido and "baja".encode() in contenido
        assert b'class="ficha' in contenido
        assert "Ver detalle".encode() in contenido

    def test_el_resultado_trae_el_panel_de_detalle_y_las_fichas_con_su_orden(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b'class="detalle-nota' in contenido
        assert b'data-orden="1"' in contenido and b'data-orden="2"' in contenido
        assert b'<button' in contenido and b'class="ficha' in contenido
        assert "Espacio: pausar".encode() in contenido

    def test_el_resultado_muestra_los_avisos_y_la_limitacion(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "confianza media es baja".encode() in contenido
        assert "una sola nota larga".encode() in contenido

    def test_el_resultado_solo_ofrece_descargar_los_archivos_que_existen(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Descargar MIDI" in contenido
        assert b"Descargar PDF" not in contenido

    def test_descargar_un_archivo_que_no_existe_da_404(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("descargar", args=[self.fragmento.pk, "pdf"]))
        assert respuesta.status_code == 404

    def test_el_estado_del_fragmento_se_consulta_en_json(self):
        respuesta = self.client.get(reverse("estado", args=[self.fragmento.pk]))
        assert respuesta.json() == {"estado": "pendiente", "paso": "", "mensaje": "", "avisos": []}

    def test_los_datos_del_lienzo_traen_notas_frases_y_pistas(self):
        self._dejar_listo()
        datos = self.client.get(reverse("datos", args=[self.fragmento.pk])).json()
        assert datos["duracion_s"] == 60.0
        assert datos["desplazamiento_s"] == 30.0
        assert [nota["nombre"] for nota in datos["notas"]] == ["G4", "B4"]
        assert [nota["etiqueta"] for nota in datos["notas"]] == ["alta", "baja"]
        assert datos["notas"][0]["cents"] == -12
        assert [nota["frase"] for nota in datos["notas"]] == [1, 2]
        assert [frase["indice"] for frase in datos["frases"]] == [1, 2]
        assert datos["pistas"] == []

    def test_los_datos_solo_listan_las_pistas_que_existen(self):
        self._dejar_listo()
        with tempfile.TemporaryDirectory() as carpeta:
            temporal = Path(carpeta) / "mezcla.wav"
            temporal.write_bytes(b"RIFF")
            self.fragmento.archivos = {**self.fragmento.archivos, "mezcla_wav": str(temporal)}
            self.fragmento.save()
            datos = self.client.get(reverse("datos", args=[self.fragmento.pk])).json()
        assert [p["clave"] for p in datos["pistas"]] == ["mezcla_wav"]

    # --- historial ---

    def test_el_historial_lista_canciones_con_sus_frases(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("historial")).content
        assert b"Huayno" in contenido
        assert reverse("cancion", args=[self.cancion.pk]).encode() in contenido
        assert reverse("detalle", args=[self.fragmento.pk]).encode() in contenido
