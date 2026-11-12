from django.contrib import admin

from .models import (
    Curso,
    Edicao,
    Entrega,
    Evento,
    EventoParticipante,
    Mentoria,
    Parceiro,
    Participacao,
    PedidoMentoria,
    PerfilMentor,
    Pessoa,
    Programa,
    Projeto,
    ProjetoParticipante,
)

# Observação LGPD: CPF não entra em list_display nem em search_fields de propósito —
# evita exibir/indexar em listagens o campo mais sensível.


@admin.register(Parceiro)
class ParceiroAdmin(admin.ModelAdmin):
    list_display = ("nome", "site")
    search_fields = ("nome",)


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("nome", "nivel")
    list_filter = ("nivel",)
    search_fields = ("nome",)


class EdicaoInline(admin.TabularInline):
    model = Edicao
    extra = 0
    fields = ("ano", "semestre", "status", "inscricoes_inicio", "inscricoes_fim", "vagas", "publicada")


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "ativo")
    list_filter = ("tipo", "ativo", "parceiros")
    search_fields = ("nome",)
    filter_horizontal = ("parceiros",)
    inlines = [EdicaoInline]


class ParticipacaoInline(admin.TabularInline):
    model = Participacao
    extra = 0
    autocomplete_fields = ("pessoa", "projeto")
    fields = ("pessoa", "papel", "status", "data_entrada", "projeto")


@admin.register(Edicao)
class EdicaoAdmin(admin.ModelAdmin):
    list_display = ("programa", "ano", "semestre", "status", "inscricoes_inicio", "inscricoes_fim", "publicada",
                    "total_participantes")
    list_filter = ("programa", "ano", "status", "publicada")
    search_fields = ("programa__nome", "ano")
    ordering = ("-ano", "-semestre")
    inlines = [ParticipacaoInline]

    @admin.display(description="Nº participantes")
    def total_participantes(self, obj):
        return obj.participacoes.count()


class PedidoInline(admin.TabularInline):
    model = PedidoMentoria
    extra = 0
    fields = ("data_pedido", "origem", "status", "projeto")
    readonly_fields = fields
    show_change_link = True
    can_delete = False


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_pessoa", "curso", "email", "telefone", "consentimento_lgpd")
    list_filter = ("tipo_pessoa", "curso", "consentimento_lgpd", "estado")
    search_fields = ("nome", "email", "emails_alternativos", "ra", "codigo_importacao")
    inlines = [PedidoInline]
    fieldsets = (
        (None, {"fields": ("nome", "tipo_pessoa", "curso", "ra", "semestre_ingresso", "ano_formacao")}),
        ("Contato", {"fields": ("email", "emails_alternativos", "telefone", "cidade", "estado", "cep")}),
        ("Documentos (dados sensíveis)", {"classes": ("collapse",),
                                          "fields": ("cpf", "rg", "data_nascimento", "cnpj")}),
        ("LGPD", {"fields": ("consentimento_lgpd", "data_consentimento")}),
        ("Outros", {"fields": ("observacoes", "codigo_importacao")}),
    )


@admin.register(PerfilMentor)
class PerfilMentorAdmin(admin.ModelAdmin):
    list_display = ("pessoa", "organizacao", "areas", "ativo", "exibir_na_vitrine")
    list_filter = ("ativo", "exibir_na_vitrine")
    search_fields = ("pessoa__nome", "areas", "organizacao")
    autocomplete_fields = ("pessoa",)


@admin.register(Participacao)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ("pessoa", "edicao", "papel", "status", "data_entrada", "projeto")
    list_filter = ("papel", "status", "edicao__programa", "edicao__ano", "vinculo_na_inscricao")
    search_fields = ("pessoa__nome",)
    autocomplete_fields = ("pessoa", "edicao", "projeto", "curso_na_inscricao")


class ProjetoParticipanteInline(admin.TabularInline):
    model = ProjetoParticipante
    extra = 0
    autocomplete_fields = ("pessoa",)


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("nome", "status", "trl_atual", "estagio", "categoria", "empresa_parceira", "origens")
    list_filter = ("status", "categoria", "estagio", "trl_atual", "edicoes__programa", "empresa_parceira")
    search_fields = ("nome", "descricao", "codigo_importacao")
    filter_horizontal = ("edicoes",)
    autocomplete_fields = ("empresa_parceira",)
    inlines = [ProjetoParticipanteInline]


class SessaoInline(admin.TabularInline):
    model = Mentoria
    extra = 0
    fields = ("data", "tipo", "responsavel", "mentor", "encaminhamentos")
    autocomplete_fields = ("mentor",)
    show_change_link = True


@admin.register(PedidoMentoria)
class PedidoMentoriaAdmin(admin.ModelAdmin):
    list_display = ("pessoa", "data_pedido", "origem", "status", "projeto", "formato", "periodo", "responsavel")
    list_filter = ("status", "origem", "ano", "formato", "periodo", "vinculo_no_pedido")
    search_fields = ("pessoa__nome", "pessoa__email", "nome_projeto_informado", "tematica")
    autocomplete_fields = ("pessoa", "projeto", "curso_no_pedido")
    date_hierarchy = "data_pedido"
    list_editable = ("status",)
    inlines = [SessaoInline]
    fieldsets = (
        (None, {"fields": ("pessoa", "data_pedido", "ano", "origem", "turma_extensao", "status", "status_detalhe",
                           "responsavel", "observacao_interna")}),
        ("O que a pessoa respondeu", {"fields": (
            "vinculo_no_pedido", "curso_no_pedido", "nome_projeto_informado", "projeto", "tematica", "desafio",
            "projeto_facens", "projeto_facens_texto", "trl", "formato", "periodo", "horario_alternativo",
            "como_soube", "como_soube_texto", "observacao", "anexo")}),
        ("Origem", {"classes": ("collapse",), "fields": ("origem_registro", "codigo_importacao")}),
    )


@admin.register(Mentoria)
class MentoriaAdmin(admin.ModelAdmin):
    list_display = ("data", "tipo", "mentorados_nomes", "responsavel", "mentor", "projeto", "encaminhamentos")
    list_filter = ("tipo", "responsavel", "edicao__programa")
    search_fields = ("mentorados__nome", "projeto__nome", "tema", "orientacao")
    autocomplete_fields = ("mentor", "mentorados", "projeto", "edicao", "pedido")
    date_hierarchy = "data"

    @admin.display(description="Mentorado(s)")
    def mentorados_nomes(self, obj):
        return ", ".join(p.nome for p in obj.mentorados.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("mentorados").select_related("mentor", "projeto")


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = ("nome", "participacao", "tipo", "status", "data_entrega")
    list_filter = ("tipo", "status")
    search_fields = ("nome", "participacao__pessoa__nome")
    autocomplete_fields = ("participacao", "projeto")


class EventoParticipanteInline(admin.TabularInline):
    model = EventoParticipante
    extra = 0
    autocomplete_fields = ("pessoa",)
    fields = ("pessoa", "status", "presente", "data_inscricao", "vinculo_na_inscricao")


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "data", "local", "publicado", "total_inscritos", "total_presentes")
    list_filter = ("tipo", "publicado", "parceiro", "edicao__programa")
    search_fields = ("nome", "local")
    date_hierarchy = "data"
    inlines = [EventoParticipanteInline]

    @admin.display(description="Inscritos")
    def total_inscritos(self, obj):
        return obj.inscricoes.count()

    @admin.display(description="Presentes")
    def total_presentes(self, obj):
        return obj.inscricoes.filter(presente=True).count()
