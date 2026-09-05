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
        assert self.fragmento.estado == Fragmento.PREPARADO

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
