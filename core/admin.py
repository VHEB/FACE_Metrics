from django.contrib import admin

from .models import (
    Parceiro,
    Curso,
    Programa,
    Edicao,
    Pessoa,
    Participacao,
    Projeto,
    ProjetoParticipante,
    Mentoria,
    Entrega,
    Evento,
    EventoParticipante,
)


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
    fields = ("ano", "semestre", "status", "data_inicio", "data_fim", "vagas")


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
    autocomplete_fields = ("pessoa",)


@admin.register(Edicao)
class EdicaoAdmin(admin.ModelAdmin):
    list_display = ("programa", "ano", "semestre", "status", "data_inicio", "data_fim", "total_participantes")
    list_filter = ("programa", "ano", "status")
    search_fields = ("programa__nome", "ano")
    ordering = ("-ano", "-semestre")
    inlines = [ParticipacaoInline]

    @admin.display(description="Nº participantes")
    def total_participantes(self, obj):
        return obj.participacoes.count()


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_pessoa", "curso", "cidade", "consentimento_lgpd")
    list_filter = ("tipo_pessoa", "curso", "consentimento_lgpd")
    search_fields = ("nome", "email", "ra")
    # CPF não entra em search_fields nem list_display de propósito:
    # evita exibir/indexar em listagens o campo mais sensível.


@admin.register(Participacao)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ("pessoa", "edicao", "papel", "status", "data_entrada", "data_saida")
    list_filter = ("papel", "status", "edicao__programa", "edicao__ano")
    search_fields = ("pessoa__nome",)
    autocomplete_fields = ("pessoa", "edicao")


class ProjetoParticipanteInline(admin.TabularInline):
    model = ProjetoParticipante
    extra = 0
    autocomplete_fields = ("pessoa",)


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "area", "estagio", "empresa_parceira")
    list_filter = ("categoria", "estagio", "area", "edicoes__programa", "empresa_parceira")
    search_fields = ("nome",)
    filter_horizontal = ("edicoes",)
    autocomplete_fields = ("empresa_parceira",)
    inlines = [ProjetoParticipanteInline]


@admin.register(Mentoria)
class MentoriaAdmin(admin.ModelAdmin):
    list_display = ("mentor", "tipo", "data", "edicao", "projeto", "duracao_minutos")
    list_filter = ("tipo", "edicao__programa", "edicao__ano")
    autocomplete_fields = ("mentor", "mentorados", "projeto", "edicao")
    date_hierarchy = "data"


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


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "data", "parceiro", "edicao", "total_inscritos", "total_presentes")
    list_filter = ("tipo", "parceiro", "edicao__programa")
    date_hierarchy = "data"
    inlines = [EventoParticipanteInline]

    @admin.display(description="Inscritos")
    def total_inscritos(self, obj):
        return obj.inscricoes.count()

    @admin.display(description="Presentes")
    def total_presentes(self, obj):
        return obj.inscricoes.filter(presente=True).count()
