"""
View principal do dashboard de métricas do FACE.

Todas as agregações usam o Django ORM (Count/annotate) direto sobre os
models existentes — nada de consulta SQL crua. O filtro por --ano usa
query string (?ano=2026), então dá pra linkar/favoritar uma visão
específica.
"""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render

from core.models import (
    Curso,
    Edicao,
    Evento,
    EventoParticipante,
    Mentoria,
    Participacao,
    Pessoa,
    Projeto,
)


@staff_member_required
def home(request):
    ano_filtro = request.GET.get("ano") or None
    anos_disponiveis = list(
        Edicao.objects.exclude(ano__isnull=True).order_by("-ano").values_list("ano", flat=True).distinct()
    )

    participacoes = Participacao.objects.all()
    mentorias = Mentoria.objects.all()
    if ano_filtro:
        participacoes = participacoes.filter(edicao__ano=ano_filtro)
        mentorias = mentorias.filter(edicao__ano=ano_filtro)

    # --- KPIs -----------------------------------------------------------
    total_pessoas = Pessoa.objects.count()
    total_participacoes = participacoes.count()
    total_projetos = Projeto.objects.count()
    total_mentorias = mentorias.count()
    total_eventos = Evento.objects.count()

    # --- Participantes por programa -------------------------------------
    por_programa = (
        participacoes.values("edicao__programa__nome")
        .annotate(total=Count("pessoa", distinct=True))
        .order_by("-total")
    )
    grafico_programa = {
        "labels": [p["edicao__programa__nome"] or "—" for p in por_programa],
        "valores": [p["total"] for p in por_programa],
    }

    # --- Participantes por curso (top 10) --------------------------------
    por_curso = (
        Pessoa.objects.exclude(curso__isnull=True)
        .values("curso__nome")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    grafico_curso = {
        "labels": [c["curso__nome"] for c in por_curso],
        "valores": [c["total"] for c in por_curso],
    }

    # --- Distribuição por tipo de pessoa ---------------------------------
    por_tipo = Pessoa.objects.values("tipo_pessoa").annotate(total=Count("id")).order_by("-total")
    tipo_labels_map = dict(Pessoa.TIPO_CHOICES)
    grafico_tipo = {
        "labels": [tipo_labels_map.get(t["tipo_pessoa"], t["tipo_pessoa"] or "—") for t in por_tipo],
        "valores": [t["total"] for t in por_tipo],
    }

    # --- Projetos por categoria -------------------------------------------
    por_categoria = Projeto.objects.values("categoria").annotate(total=Count("id")).order_by("-total")
    categoria_labels_map = dict(Projeto.CATEGORIA_CHOICES)
    grafico_categoria = {
        "labels": [categoria_labels_map.get(c["categoria"], "Não classificado") if c["categoria"] else "Não classificado" for c in por_categoria],
        "valores": [c["total"] for c in por_categoria],
    }

    # --- Projetos por estágio ----------------------------------------------
    por_estagio = Projeto.objects.values("estagio").annotate(total=Count("id")).order_by("-total")
    estagio_labels_map = dict(Projeto.ESTAGIO_CHOICES)
    grafico_estagio = {
        "labels": [estagio_labels_map.get(e["estagio"], e["estagio"]) for e in por_estagio],
        "valores": [e["total"] for e in por_estagio],
    }

    # --- Mentorias: diagnóstico vs acompanhamento, por ano ------------------
    mentorias_por_ano_tipo = (
        Mentoria.objects.exclude(edicao__ano__isnull=True)
        .values("edicao__ano", "tipo")
        .annotate(total=Count("id"))
    )
    anos_mentoria = sorted({m["edicao__ano"] for m in mentorias_por_ano_tipo})
    grafico_mentorias = {
        "labels": [str(a) for a in anos_mentoria],
        "diagnostico": [
            sum(m["total"] for m in mentorias_por_ano_tipo if m["edicao__ano"] == ano and m["tipo"] == "diagnostico")
            for ano in anos_mentoria
        ],
        "acompanhamento": [
            sum(m["total"] for m in mentorias_por_ano_tipo if m["edicao__ano"] == ano and m["tipo"] == "acompanhamento")
            for ano in anos_mentoria
        ],
    }

    # --- Presença em eventos -------------------------------------------------
    total_inscricoes_evento = EventoParticipante.objects.count()
    total_presentes_evento = EventoParticipante.objects.filter(presente=True).count()
    taxa_presenca = (
        round((total_presentes_evento / total_inscricoes_evento) * 100, 1) if total_inscricoes_evento else 0
    )

    contexto = {
        "anos_disponiveis": anos_disponiveis,
        "ano_filtro": int(ano_filtro) if ano_filtro else None,
        "total_pessoas": total_pessoas,
        "total_participacoes": total_participacoes,
        "total_projetos": total_projetos,
        "total_mentorias": total_mentorias,
        "total_eventos": total_eventos,
        "taxa_presenca": taxa_presenca,
        "total_inscricoes_evento": total_inscricoes_evento,
        "total_presentes_evento": total_presentes_evento,
        "grafico_programa_json": json.dumps(grafico_programa),
        "grafico_curso_json": json.dumps(grafico_curso),
        "grafico_tipo_json": json.dumps(grafico_tipo),
        "grafico_categoria_json": json.dumps(grafico_categoria),
        "grafico_estagio_json": json.dumps(grafico_estagio),
        "grafico_mentorias_json": json.dumps(grafico_mentorias),
    }
    return render(request, "dashboard/home.html", contexto)
