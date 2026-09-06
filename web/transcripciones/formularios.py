import re

from django import forms

_PATRON = re.compile(r"^(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parsear_tiempo(texto) -> float:
    """Acepta '90', '1:30' y '1:30.5'. Devuelve segundos.

    Sin minutos, los segundos son libres ('90' son 90 s). Con minutos, los
    segundos van de 0 a 59, como en un reloj ('1:75' no vale).
    """
    coincidencia = _PATRON.match(str(texto).strip())
    if not coincidencia:
        raise ValueError(f"tiempo inválido: {texto!r}. Usa el formato 1:30")
    minutos, segundos = coincidencia.groups()
    if minutos is not None and float(segundos) >= 60:
        raise ValueError(f"tiempo inválido: {texto!r}. Los segundos van de 0 a 59")
    return (int(minutos) if minutos else 0) * 60 + float(segundos)


class FormularioCancion(forms.Form):
    url = forms.CharField(required=False)
    archivo = forms.FileField(required=False)

    def clean(self):
        datos = super().clean()
        if not (datos.get("url") or "").strip() and not datos.get("archivo"):
            raise forms.ValidationError("Pega un enlace de YouTube o sube un archivo.")
        return datos
