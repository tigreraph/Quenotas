from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("historial/", views.historial, name="historial"),
    path("cancion/<int:pk>/", views.cancion, name="cancion"),
    path("cancion/<int:pk>/estado/", views.cancion_estado, name="cancion_estado"),
    path("cancion/<int:pk>/onda/", views.cancion_onda, name="cancion_onda"),
    path("cancion/<int:pk>/escucha/", views.cancion_escucha, name="cancion_escucha"),
    path("cancion/<int:pk>/frases/", views.crear_frase, name="crear_frase"),
    path("cancion/<int:pk>/reintentar/", views.cancion_reintentar, name="cancion_reintentar"),
    path("fragmento/<int:pk>/", views.detalle, name="detalle"),
    path("fragmento/<int:pk>/estado/", views.estado, name="estado"),
    path("fragmento/<int:pk>/reintentar/", views.reintentar, name="reintentar"),
    path("fragmento/<int:pk>/datos/", views.datos, name="datos"),
    path("fragmento/<int:pk>/audio/<str:clave>/", views.audio, name="audio"),
    path("fragmento/<int:pk>/descargar/<str:clave>/", views.descargar, name="descargar"),
]
