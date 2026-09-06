import gc
import tempfile
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase

from transcripciones.audio_http import respuesta_audio


def _cuerpo(respuesta) -> bytes:
    if hasattr(respuesta, "streaming_content"):
        return b"".join(respuesta.streaming_content)
    return respuesta.content


class PruebaRange(SimpleTestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.ruta = Path(self.carpeta.name) / "pista.wav"
        self.ruta.write_bytes(bytes(range(256)) * 4)   # 1024 bytes conocidos
        self.fabrica = RequestFactory()

    def tearDown(self):
        gc.collect()  # Forzar la liberación de archivos abiertos en FileResponse
        self.carpeta.cleanup()

    def test_sin_range_devuelve_todo_y_anuncia_que_acepta_rangos(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a"))
        assert respuesta.status_code == 200
        assert respuesta["Accept-Ranges"] == "bytes"
        assert respuesta["Content-Length"] == "1024"
        assert respuesta["Content-Type"] == "audio/wav"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()

    def test_un_rango_cerrado_devuelve_206_con_content_range(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=0-99"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 0-99/1024"
        assert respuesta["Content-Length"] == "100"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()[:100]

    def test_un_rango_abierto_llega_hasta_el_final(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=1000-"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 1000-1023/1024"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()[1000:]

    def test_un_sufijo_devuelve_los_ultimos_bytes(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=-24"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 1000-1023/1024"

    def test_un_rango_fuera_del_archivo_da_416(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=5000-"))
        assert respuesta.status_code == 416
        assert respuesta["Content-Range"] == "bytes */1024"

    def test_el_tipo_sale_de_la_extension(self):
        m4a = self.ruta.with_suffix(".m4a")
        m4a.write_bytes(b"x" * 10)
        respuesta = respuesta_audio(m4a, self.fabrica.get("/a"))
        assert respuesta["Content-Type"] == "audio/mp4"
