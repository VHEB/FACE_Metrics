from django import forms

from core.models import Evento, Mentoria, Pessoa, Projeto


class BootstrapFormMixin:
    """Aplica classes do Bootstrap em todos os campos automaticamente, sem precisar repetir em cada Form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
                widget.attrs.setdefault("rows", 3)
            else:
                widget.attrs.setdefault("class", "form-control")


class EventoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["nome", "tipo", "data", "local", "parceiro", "edicao"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
        }


class MentoriaForm(BootstrapFormMixin, forms.ModelForm):
    mentorados = forms.ModelMultipleChoiceField(
        queryset=Pessoa.objects.order_by("nome"),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 10, "id": "id_mentorados"}),
        label="Mentorado(s)",
        help_text="Segure Ctrl (ou Cmd no Mac) para selecionar mais de uma pessoa. Use a busca acima para filtrar.",
    )

    class Meta:
        model = Mentoria
        fields = ["tipo", "edicao", "projeto", "data", "duracao_minutos", "tema", "observacoes", "mentorados"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
        }

    def save(self, commit=True):
        mentoria = super().save(commit=commit)
        if commit:
            mentoria.mentorados.set(self.cleaned_data["mentorados"])
        return mentoria


class PessoaQuickForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Pessoa
        fields = ["nome", "email", "telefone", "tipo_pessoa", "curso", "ra", "cidade"]


class PessoaBuscaForm(forms.Form):
    q = forms.CharField(required=False, label="Buscar por nome, e-mail ou RA")
    tipo_pessoa = forms.ChoiceField(
        required=False, choices=[("", "Todos os vínculos")] + list(Pessoa.TIPO_CHOICES),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            )


class ProjetoBuscaForm(forms.Form):
    q = forms.CharField(required=False, label="Buscar por nome do projeto")
    categoria = forms.ChoiceField(required=False, choices=[("", "Todas as categorias")] + list(Projeto.CATEGORIA_CHOICES))
    estagio = forms.ChoiceField(required=False, choices=[("", "Todos os estágios")] + list(Projeto.ESTAGIO_CHOICES))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            )
