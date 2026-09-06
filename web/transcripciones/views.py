import json
from pathlib import Path

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from motor.config import Config
from motor.contrato import formato_tiempo

from . import trabajos
from .audio_http import respuesta_audio
from .formularios import FormularioCancion, parsear_tiempo
from .models import Cancion, Fragmento

NOMBRES_DESCARGA = {"midi": "melodia.mid", "txt": "notas.txt", "pdf": "notas.pdf"}
SELECCION_MINIMA_S = 1.0
TOLERANCIA_FIN_S = 0.25   # la misma que recortar()


# --- inicio ---

def index(request):
    # Se vincula siempre que sea POST: con `request.POST or None` un envío
    # vacío (QueryDict vacío es falsy) dejaría el formulario sin vincular y
    # el error "Pega un enlace o sube un archivo" nunca se mostraría.
    es_envio = request.method == "POST"
    formulario = FormularioCancion(
        request.POST if es_envio else None, request.FILES if es_envio else None,
    )
    if es_envio and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("archivo"):
            ruta = _guardar_subida(datos["archivo"])
            cancion = Cancion.objects.create(
                titulo=ruta.stem, fuente="archivo", referencia=ruta.name, origen=str(ruta),
            )
        else:
            url = datos["url"].strip()
            # La misma URL es la misma canción: la descarga ya está en caché y
            # el historial no se llena de repeticiones.
            cancion = Cancion.objects.filter(fuente="youtube", referencia=url).first()
            if cancion is None:
                cancion = Cancion.objects.create(titulo="", fuente="youtube", referencia=url, origen=url)
            elif not cancion.origen:
                Cancion.objects.filter(pk=cancion.pk).update(origen=url)
                cancion.origen = url
        _preparar_si_hace_falta(cancion)
        return redirect("cancion", pk=cancion.pk)

    return render(request, "transcripciones/index.html", {
        "formulario": formulario,
        "recientes": Cancion.objects.all()[:8],
    })


def _guardar_subida(archivo) -> Path:
    """default_storage añade un sufijo si ya existe un archivo con ese nombre."""
    nombre = default_storage.save(f"subidas/{archivo.name}", archivo)
    return Path(default_storage.path(nombre))


def _preparar_si_hace_falta(cancion):
    """Lanza la preparación salvo que ya esté lista o en marcha. Atómico."""
    actualizados = Cancion.objects.filter(pk=cancion.pk).exclude(
        estado__in=[Cancion.LISTA, Cancion.PREPARANDO]
    ).update(estado=Cancion.PREPARANDO, paso="Preparando", mensaje="")
    if actualizados:
        trabajos.lanzar_preparacion_cancion(cancion.pk)


# --- canción ---

def cancion(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    if cancion.estado == Cancion.PENDIENTE and cancion.origen:
        _preparar_si_hace_falta(cancion)
        cancion.refresh_from_db()
    return render(request, "transcripciones/cancion.html", {
        "cancion": cancion,
        "frases": [
            {
                "pk": f.pk,
                "rango": f"{formato_tiempo(f.inicio_s)} a {formato_tiempo(f.fin_s)}",
                "estado": f.get_estado_display(),
            }
            for f in cancion.frases()
        ],
        "duracion": formato_tiempo(cancion.duracion_s or 0),
    })


def _frase_a_dict(fragmento):
    return {
        "id": fragmento.pk,
        "inicio_s": fragmento.inicio_s,
        "fin_s": fragmento.fin_s,
        "estado": fragmento.estado,
        "etiqueta": fragmento.get_estado_display(),
        "paso": fragmento.paso,
        "mensaje": fragmento.mensaje,
        "url": reverse("detalle", args=[fragmento.pk]),
        "reintentar": reverse("reintentar", args=[fragmento.pk]),
    }


def cancion_estado(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    return JsonResponse({
        "estado": cancion.estado,
        "paso": cancion.paso,
        "mensaje": cancion.mensaje,
        "titulo": cancion.titulo,
        "duracion_s": cancion.duracion_s,
        "max_fragmento_s": Config.desde_entorno().max_fragmento_s,
        "separar": cancion.separar,
        "frases": [_frase_a_dict(f) for f in cancion.frases()],
    })


def cancion_onda(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    ruta = trabajos.directorio_cancion(cancion) / "onda.json"
    if not cancion.lista or not ruta.exists():
        raise Http404("la forma de onda todavía no existe")
    return JsonResponse({
        "duracion_s": cancion.duracion_s,
        "picos": json.loads(ruta.read_text(encoding="utf-8")),
    })


def cancion_escucha(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    if not cancion.audio_escucha or not Path(cancion.audio_escucha).exists():
        raise Http404("el audio de escucha todavía no existe")
    return respuesta_audio(cancion.audio_escucha, request)


def _leer_tiempo(texto) -> float:
    """Acepta segundos con decimales ('10.5') o m:ss ('1:30')."""
    texto = str(texto or "").strip()
    try:
        return float(texto)
    except ValueError:
        return parsear_tiempo(texto)


@require_POST
def crear_frase(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    if not cancion.lista:
        return JsonResponse({"error": "La canción todavía no está lista."}, status=409)
    try:
        inicio = _leer_tiempo(request.POST.get("inicio_s"))
        fin = _leer_tiempo(request.POST.get("fin_s"))
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    if inicio < 0:
        return JsonResponse({"error": "El inicio no puede ser negativo."}, status=400)
    limite = Config.desde_entorno().max_fragmento_s
    if fin <= inicio:
        return JsonResponse({"error": "El final debe ser posterior al inicio."}, status=400)
    if fin - inicio < SELECCION_MINIMA_S:
        return JsonResponse({"error": "La selección debe durar al menos 1 segundo."}, status=400)
    if fin - inicio > limite:
        return JsonResponse({"error": f"La selección dura {fin - inicio:.0f} s y el límite es {limite:.0f} s."}, status=400)
    if cancion.duracion_s is not None and fin > cancion.duracion_s + TOLERANCIA_FIN_S:
        return JsonResponse({"error": "La selección termina después del final de la canción."}, status=400)

    separar = str(request.POST.get("separar", "true")).lower() in ("true", "on", "1")
    fragmento = Fragmento.objects.create(
        cancion=cancion, origen=cancion.origen, inicio_s=inicio, fin_s=fin, separar=separar,
        estado=Fragmento.PROCESANDO, paso="En cola",
    )
    Cancion.objects.filter(pk=cancion.pk).update(separar=separar)
    trabajos.lanzar_frase(fragmento.pk)
    return JsonResponse(_frase_a_dict(fragmento), status=201)


@require_POST
def cancion_reintentar(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    actualizados = Cancion.objects.filter(
        pk=pk, estado__in=[Cancion.ERROR, Cancion.PENDIENTE]
    ).update(estado=Cancion.PREPARANDO, paso="Preparando", mensaje="")
    if actualizados:
        trabajos.lanzar_preparacion_cancion(cancion.pk)
    return redirect("cancion", pk=pk)


# --- fragmento (frase) ---

def detalle(request, pk):
    fragmento = get_object_or_404(Fragmento.objects.select_related("cancion"), pk=pk)
    return render(request, "transcripciones/detalle.html", {
        "fragmento": fragmento,
        "frases": fragmento.por_frases(),
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
def reintentar(request, pk):
    """Desde error: vuelve a recortar y analizar. Atómico para no lanzar dos veces."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    actualizados = Fragmento.objects.filter(pk=pk, estado=Fragmento.ERROR).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    if actualizados:
        trabajos.lanzar_frase(fragmento.pk)
    return redirect("detalle", pk=pk)


def historial(request):
    return render(request, "transcripciones/historial.html", {
        "canciones": Cancion.objects.prefetch_related("fragmentos"),
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
    """Entrega el audio para reproducirlo en la página, con soporte de Range."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    return respuesta_audio(_archivo_de(fragmento, clave), request)


ETIQUETAS_PISTA = (
    ("mezcla_wav", "Mezcla original"),
    ("melodia_wav", "Melodía aislada"),
    ("notas_wav", "Notas detectadas"),
)


def datos(request, pk):
    """Todo lo que el lienzo de notas necesita, en una sola petición."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    pistas = [
        {"clave": clave, "etiqueta": etiqueta, "url": reverse("audio", args=[fragmento.pk, clave])}
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
                "cents": nota.cents,
                "frase": nota.frase,
            }
            for nota in fragmento.notas.all()
        ],
        "frases": frases,
        "pistas": pistas,
    })
