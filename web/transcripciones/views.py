from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from motor.contrato import formato_tiempo

from . import trabajos
from .formularios import FormularioFragmento
from .models import Cancion, Fragmento

NOMBRES_DESCARGA = {"midi": "melodia.mid", "txt": "notas.txt", "pdf": "notas.pdf"}


def index(request):
    formulario = FormularioFragmento(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("archivo"):
            origen = _guardar_subida(datos["archivo"])
            cancion = Cancion.objects.create(
                titulo=Path(origen.name).stem, fuente="archivo", referencia=origen.name,
            )
        else:
            origen = datos["url"].strip()
            # La misma URL cuelga de la misma canción: el historial no se llena
            # de repeticiones y la descarga ya está en caché.
            cancion = Cancion.objects.filter(fuente="youtube", referencia=origen).first()
            if cancion is None:
                cancion = Cancion.objects.create(titulo="", fuente="youtube", referencia=origen)
        fragmento = Fragmento.objects.create(
            cancion=cancion, origen=str(origen),
            inicio_s=datos["inicio_s"], fin_s=datos["fin_s"],
            separar=bool(datos.get("separar")),
        )
        trabajos.lanzar_preparacion(fragmento.pk, str(origen))
        return redirect("detalle", pk=fragmento.pk)

    return render(request, "transcripciones/index.html", {
        "formulario": formulario,
        "recientes": Fragmento.objects.select_related("cancion")[:8],
    })


def _guardar_subida(archivo) -> Path:
    """default_storage añade un sufijo si ya existe un archivo con ese nombre,
    así dos grabaciones llamadas 'ensayo.m4a' no se pisan."""
    nombre = default_storage.save(f"subidas/{archivo.name}", archivo)
    return Path(default_storage.path(nombre))


def detalle(request, pk):
    fragmento = get_object_or_404(Fragmento.objects.select_related("cancion"), pk=pk)
    return render(request, "transcripciones/detalle.html", {
        "fragmento": fragmento,
        "frases": fragmento.por_frases(),
        "desplazamiento": fragmento.inicio_s,
        "rango": f"{formato_tiempo(fragmento.inicio_s)} a {formato_tiempo(fragmento.fin_s)}",
    })


def estado(request, pk):
    fragmento = get_object_or_404(Fragmento, pk=pk)
    return JsonResponse({
        "estado": fragmento.estado,
        "paso": fragmento.paso,
        "mensaje": fragmento.mensaje,
        "avisos": fragmento.avisos,
    })


@require_POST
def analizar(request, pk):
    fragmento = get_object_or_404(Fragmento, pk=pk)
    if fragmento.estado == Fragmento.PREPARADO:
        trabajos.lanzar_analisis(fragmento.pk)
    return redirect("detalle", pk=pk)


@require_POST
def reintentar(request, pk):
    """Desde error: si ya hay recorte, vuelve a analizar; si no, vuelve a preparar."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    if fragmento.estado == Fragmento.ERROR:
        if fragmento.archivos.get("mezcla_wav"):
            fragmento.estado = Fragmento.PREPARADO
            fragmento.mensaje = ""
            fragmento.save(update_fields=["estado", "mensaje"])
            trabajos.lanzar_analisis(fragmento.pk)
        else:
            trabajos.lanzar_preparacion(fragmento.pk, fragmento.origen)
    return redirect("detalle", pk=pk)


def historial(request):
    return render(request, "transcripciones/historial.html", {
        "fragmentos": Fragmento.objects.select_related("cancion"),
    })


def _archivo_de(fragmento, clave) -> Path:
    ruta = fragmento.archivos.get(clave)
    if not ruta or not Path(ruta).exists():
        raise Http404("ese archivo no existe todavía")
    return Path(ruta)


def descargar(request, pk, clave):
    """Entrega el archivo como descarga."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    ruta = _archivo_de(fragmento, clave)
    return FileResponse(open(ruta, "rb"), as_attachment=True,
                        filename=NOMBRES_DESCARGA.get(clave, ruta.name))


def audio(request, pk, clave):
    """Entrega el audio para reproducirlo en la página, no para descargarlo."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    ruta = _archivo_de(fragmento, clave)
    return FileResponse(open(ruta, "rb"), content_type="audio/wav")


ETIQUETAS_PISTA = (
    ("mezcla_wav", "Mezcla original"),
    ("melodia_wav", "Melodía aislada"),
    ("notas_wav", "Notas detectadas"),
)


def datos(request, pk):
    """Todo lo que el lienzo necesita, en una sola petición."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    pistas = [
        {
            "clave": clave,
            "etiqueta": etiqueta,
            "url": reverse("audio", args=[fragmento.pk, clave]),
        }
        for clave, etiqueta in ETIQUETAS_PISTA
        if fragmento.archivos.get(clave) and Path(fragmento.archivos[clave]).exists()
    ]
    frases = [
        {"indice": indice, "inicio_s": notas[0].inicio_s, "fin_s": notas[-1].fin_s}
        for indice, notas in fragmento.por_frases()
    ]
    return JsonResponse({
        "duracion_s": fragmento.duracion_s,
        "desplazamiento_s": fragmento.inicio_s,
        "notas": [
            {
                "orden": nota.orden,
                "nombre": nota.nombre,
                "midi": nota.midi,
                "inicio_s": nota.inicio_s,
                "duracion_s": nota.duracion_s,
                "confianza": nota.confianza,
                "etiqueta": nota.etiqueta_confianza,
            }
            for nota in fragmento.notas.all()
        ],
        "frases": frases,
        "pistas": pistas,
    })
