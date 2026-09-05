from django.contrib import admin

from .models import Cancion, Fragmento, Nota

admin.site.register(Cancion)
admin.site.register(Fragmento)
admin.site.register(Nota)
