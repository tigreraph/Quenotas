from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("historial/", views.historial, name="historial"),
    path("fragmento/<int:pk>/", views.detalle, name="detalle"),
    path("fragmento/<int:pk>/estado/", views.estado, name="estado"),
    path("fragmento/<int:pk>/analizar/", views.analizar, name="analizar"),
    path("fragmento/<int:pk>/reintentar/", views.reintentar, name="reintentar"),
    path("fragmento/<int:pk>/datos/", views.datos, name="datos"),
    path("fragmento/<int:pk>/audio/<str:clave>/", views.audio, name="audio"),
    path("fragmento/<int:pk>/descargar/<str:clave>/", views.descargar, name="descargar"),
]
