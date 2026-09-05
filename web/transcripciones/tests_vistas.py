import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.urls import reverse

from transcripciones.formularios import parsear_tiempo
from transcripciones.models import Cancion, Fragmento


def test_parsear_tiempo_acepta_los_tres_formatos():
    assert parsear_tiempo("90") == 90.0
    assert parsear_tiempo("1:30") == 90.0
    assert parsear_tiempo("1:30.5") == 90.5
    assert parsear_tiempo("0:07") == 7.0


def test_parsear_tiempo_rechaza_basura():
    for texto in ["", "abc", "1:2:3", "-5", "1:75"]:
        with pytest.raises(ValueError):
            parsear_tiempo(texto)


class PruebaVistas(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(titulo="Huayno", fuente="youtube",
                                              referencia="https://youtu.be/abc")
        self.fragmento = Fragmento.objects.create(cancion=self.cancion, origen="https://youtu.be/abc",
                                                  inicio_s=30.0, fin_s=90.0, separar=True)

    def test_el_index_responde(self):
        respuesta = self.client.get(reverse("index"))
        assert respuesta.status_code == 200
        assert b"YouTube" in respuesta.content

    def test_enviar_una_url_crea_el_fragmento_y_lanza_la_preparacion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            respuesta = self.client.post(reverse("index"), {
                "url": "https://youtu.be/xyz",
                "inicio": "0:30",
                "fin": "1:30",
                "separar": "on",
            })
        assert respuesta.status_code == 302
        creado = Fragmento.objects.exclude(pk=self.fragmento.pk).get()
        assert creado.inicio_s == 30.0
        assert creado.fin_s == 90.0
        assert creado.separar is True
        lanzar.assert_called_once_with(creado.pk, "https://youtu.be/xyz")

    def test_un_rango_invertido_no_crea_nada(self):
        respuesta = self.client.post(reverse("index"), {
            "url": "https://youtu.be/xyz", "inicio": "1:30", "fin": "0:30",
        })
        assert respuesta.status_code == 200
        assert Fragmento.objects.count() == 1

    def test_un_fragmento_mas_largo_que_el_limite_se_rechaza(self):
        respuesta = self.client.post(reverse("index"), {
            "url": "https://youtu.be/xyz", "inicio": "0:00", "fin": "10:00",
        })
        assert respuesta.status_code == 200
        assert b"181" in respuesta.content or b"180" in respuesta.content

    def test_el_estado_se_consulta_en_json(self):
        respuesta = self.client.get(reverse("estado", args=[self.fragmento.pk]))
        assert respuesta.json() == {
            "estado": "pendiente", "paso": "", "mensaje": "", "avisos": []
        }

    def test_analizar_lanza_el_trabajo_solo_si_esta_preparado(self):
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            lanzar.assert_not_called()

        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            respuesta = self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302

    def test_analizar_deja_el_fragmento_procesando_y_no_se_lanza_dos_veces(self):
        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            lanzar.assert_called_once()
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PROCESANDO
        assert self.fragmento.paso == "En cola"

    def test_el_detalle_muestra_el_reproductor_cuando_esta_preparado(self):
        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        respuesta = self.client.get(reverse("detalle", args=[self.fragmento.pk]))
        assert b"Analizar" in respuesta.content

    def test_el_detalle_muestra_el_mensaje_de_error(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.mensaje = "No se pudo descargar el audio del enlace"
        self.fragmento.save()
        respuesta = self.client.get(reverse("detalle", args=[self.fragmento.pk]))
        assert "No se pudo descargar".encode() in respuesta.content

    def test_la_misma_url_reutiliza_la_cancion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion"):
            self.client.post(reverse("index"), {
                "url": "https://youtu.be/abc", "inicio": "1:30", "fin": "2:00",
            })
        assert Cancion.objects.filter(referencia="https://youtu.be/abc").count() == 1
        nuevo = Fragmento.objects.exclude(pk=self.fragmento.pk).get()
        assert nuevo.cancion == self.cancion
        assert nuevo.origen == "https://youtu.be/abc"

    def test_reintentar_relanza_el_analisis_si_ya_hay_recorte(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            respuesta = self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PROCESANDO

    def test_reintentar_relanza_la_preparacion_si_no_hay_recorte(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.archivos = {}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk, "https://youtu.be/abc")

    def test_reintentar_no_hace_nada_si_no_esta_en_error(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_not_called()

    def _dejar_listo(self):
        from transcripciones.models import Nota
        self.fragmento.estado = Fragmento.LISTO
        self.fragmento.archivos = {"midi": "media/x.mid", "txt": "media/x.txt"}
        self.fragmento.avisos = ["La confianza media es baja."]
        self.fragmento.save()
        Nota.objects.create(fragmento=self.fragmento, frase=1, orden=1, nombre="G4",
                            midi=67, inicio_s=0.4, duracion_s=0.42, confianza=0.93, cents=-12)
        Nota.objects.create(fragmento=self.fragmento, frase=2, orden=2, nombre="B4",
                            midi=71, inicio_s=2.0, duracion_s=0.60, confianza=0.40, cents=30)

    def test_el_resultado_muestra_las_notas_agrupadas_por_frase(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Frase 1" in contenido and b"Frase 2" in contenido
        assert b"G4" in contenido and b"B4" in contenido
        assert "alta".encode() in contenido and "baja".encode() in contenido

    def test_el_resultado_muestra_los_avisos(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "confianza media es baja".encode() in contenido

    def test_el_resultado_avisa_de_las_notas_repetidas(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "una sola nota larga".encode() in contenido

    def test_el_resultado_solo_ofrece_descargar_los_archivos_que_existen(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Descargar MIDI" in contenido
        assert b"Descargar PDF" not in contenido

    def test_un_rango_invertido_sin_separar_no_deja_la_casilla_marcada(self):
        respuesta = self.client.post(reverse("index"), {
            "url": "https://youtu.be/xyz", "inicio": "1:30", "fin": "0:30",
        })
        assert respuesta.status_code == 200
        assert b'name="separar"' in respuesta.content
        assert b'name="separar" checked' not in respuesta.content

    def test_el_index_por_get_trae_la_casilla_marcada(self):
        respuesta = self.client.get(reverse("index"))
        assert b'name="separar" checked' in respuesta.content

    def test_descargar_un_archivo_que_no_existe_da_404(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("descargar", args=[self.fragmento.pk, "pdf"]))
        assert respuesta.status_code == 404

    def test_el_historial_lista_los_fragmentos(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("historial")).content
        assert b"Huayno" in contenido

    def test_los_datos_del_lienzo_traen_notas_frases_y_pistas(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("datos", args=[self.fragmento.pk]))
        datos = respuesta.json()
        assert datos["duracion_s"] == 60.0
        assert datos["desplazamiento_s"] == 30.0
        assert [nota["nombre"] for nota in datos["notas"]] == ["G4", "B4"]
        assert datos["notas"][0]["inicio_s"] == 0.4
        assert [nota["etiqueta"] for nota in datos["notas"]] == ["alta", "baja"]
        assert [frase["indice"] for frase in datos["frases"]] == [1, 2]
        assert datos["frases"][1]["inicio_s"] == 2.0
        assert datos["frases"][1]["fin_s"] == 2.6
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
        assert datos["pistas"][0]["etiqueta"] == "Mezcla original"
