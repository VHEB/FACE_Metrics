from django import forms

from core.models import Evento, Mentoria, PedidoMentoria, Pessoa, Projeto


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
        fields = ["nome", "tipo", "data", "local", "ponto_encontro", "vagas", "inscricoes_inicio", "inscricoes_fim",
                  "publicado", "descricao", "parceiro", "edicao", "observacoes"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "inscricoes_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "inscricoes_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
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
        fields = ["tipo", "pedido", "edicao", "projeto", "data", "horario", "duracao_minutos", "responsavel",
                  "tema", "orientacao", "encaminhamentos", "observacoes", "mentorados"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "horario": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pedido"].queryset = PedidoMentoria.objects.select_related("pessoa").exclude(
            status__in=["realizado", "nao_realizado"]).order_by("-data_pedido")
        self.fields["pedido"].help_text = "Pedidos ainda em aberto. Ao registrar a sessão, o pedido vira 'Realizado'."
        self.fields["data"].required = True

    def save(self, commit=True):
        mentoria = super().save(commit=commit)
        if commit:
            mentoria.mentorados.set(self.cleaned_data["mentorados"])
            pedido = mentoria.pedido
            if pedido and pedido.status != "realizado":
                pedido.status = "realizado"
                pedido.save(update_fields=["status", "atualizado_em"])
        return mentoria


class PedidoAtendimentoForm(BootstrapFormMixin, forms.ModelForm):
    """Campos que a equipe atualiza ao acompanhar um pedido de mentoria."""

    class Meta:
        model = PedidoMentoria
        fields = ["status", "responsavel", "projeto", "observacao_interna"]


class PedidoBuscaForm(forms.Form):
    q = forms.CharField(required=False, label="Buscar por nome, projeto ou temática")
    status = forms.ChoiceField(required=False, choices=[("", "Todos os status")] + PedidoMentoria.STATUS_CHOICES)
    origem = forms.ChoiceField(required=False, choices=[("", "Todas as origens")] + PedidoMentoria.ORIGEM_CHOICES)
    ano = forms.TypedChoiceField(required=False, coerce=int, empty_value=None, choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anos = PedidoMentoria.objects.order_by("-ano").values_list("ano", flat=True).distinct()
        self.fields["ano"].choices = [("", "Todos os anos")] + [(a, a) for a in anos]
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            )


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
