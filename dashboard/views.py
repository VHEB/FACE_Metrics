"""
View principal do dashboard de métricas do FACE.

Todas as agregações usam o Django ORM (Count/annotate) direto sobre os
models existentes — nada de consulta SQL crua. O filtro por --ano usa
query string (?ano=2026), então dá pra linkar/favoritar uma visão
específica.
"""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.shortcuts import render

from core.models import (
    Curso,
    Edicao,
    Evento,
    EventoParticipante,
    Mentoria,
    Participacao,
    PedidoMentoria,
    Pessoa,
    Projeto,
)


@staff_member_required
def home(request):
    ano_filtro = request.GET.get("ano") or None
    if ano_filtro and not str(ano_filtro).isdigit():
        ano_filtro = None
    anos_disponiveis = sorted(
        set(Edicao.objects.values_list("ano", flat=True))
        | set(PedidoMentoria.objects.values_list("ano", flat=True))
        | {d.year for d in Mentoria.objects.dates("data", "year")}
        | {d.year for d in Evento.objects.dates("data", "year")},
        reverse=True,
    )

    # Com ano escolhido, TODOS os números abaixo passam a ser daquele ano.
    participacoes = Participacao.objects.all()
    mentorias = Mentoria.objects.all()
    pedidos = PedidoMentoria.objects.all()
    inscricoes_eventos = EventoParticipante.objects.all()
    eventos = Evento.objects.all()
    if ano_filtro:
        participacoes = participacoes.filter(edicao__ano=ano_filtro)
        mentorias = mentorias.filter(data__year=ano_filtro)
        pedidos = pedidos.filter(ano=ano_filtro)
        inscricoes_eventos = inscricoes_eventos.filter(evento__data__year=ano_filtro)
        eventos = eventos.filter(data__year=ano_filtro)
        ids_atendidos = (
            set(participacoes.values_list("pessoa_id", flat=True))
            | set(pedidos.values_list("pessoa_id", flat=True))
            | set(mentorias.values_list("mentorados__id", flat=True))
            | set(inscricoes_eventos.values_list("pessoa_id", flat=True))
        )
        pessoas = Pessoa.objects.filter(id__in=ids_atendidos)
        projetos = Projeto.objects.filter(
            Q(edicoes__ano=ano_filtro) | Q(pedidos_mentoria__ano=ano_filtro) | Q(mentorias__data__year=ano_filtro)
        ).distinct()
    else:
        pessoas = Pessoa.objects.exclude(tipo_pessoa="mentor_parceiro")
        projetos = Projeto.objects.all()

    # --- KPIs -----------------------------------------------------------
    total_pessoas = pessoas.count()
    total_participacoes = participacoes.count()
    total_projetos = projetos.count()
    total_mentorias = mentorias.count()
    total_eventos = eventos.count()
    total_pedidos = pedidos.count()
    pedidos_realizados = pedidos.filter(status="realizado").count()
    taxa_atendimento = round(100 * pedidos_realizados / total_pedidos) if total_pedidos else 0

    # --- Participantes por programa -------------------------------------
    por_programa = (
        participacoes.values("edicao__programa__nome")
        .annotate(total=Count("pessoa", distinct=True))
        .order_by("-total")
    )
    linhas = [(p["edicao__programa__nome"] or "—", p["total"]) for p in por_programa]
    # mentorias e viagens não são "edições", mas também são atendimento: entram no mesmo gráfico
    origem_labels = dict(PedidoMentoria.ORIGEM_CHOICES)
    for o in pedidos.values("origem").annotate(total=Count("pessoa", distinct=True)):
        linhas.append((f"Mentorias — {origem_labels.get(o['origem'], o['origem'])}", o["total"]))
    viajantes = inscricoes_eventos.filter(evento__tipo="viagem").values("pessoa").distinct().count()
    if viajantes:
        linhas.append(("Viagens", viajantes))
    linhas.sort(key=lambda x: -x[1])
    grafico_programa = {"labels": [l for l, _ in linhas], "valores": [v for _, v in linhas]}

    # --- Participantes por curso (top 10) --------------------------------
    por_curso = (
        pessoas.exclude(curso__isnull=True)
        .values("curso__nome")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    grafico_curso = {
        "labels": [c["curso__nome"].replace("Tecnologia em ", "Tec. em ").replace("Análise e Desenvolvimento de Sistemas", "ADS")
                   for c in por_curso],
        "valores": [c["total"] for c in por_curso],
    }

    # --- Distribuição por tipo de pessoa ---------------------------------
    por_tipo = pessoas.values("tipo_pessoa").annotate(total=Count("id")).order_by("-total")
    tipo_labels_map = dict(Pessoa.TIPO_CHOICES)
    grafico_tipo = {
        "labels": [tipo_labels_map.get(t["tipo_pessoa"], t["tipo_pessoa"] or "Não informado") for t in por_tipo],
        "valores": [t["total"] for t in por_tipo],
    }

    # --- Pedidos de mentoria por status (gráfico que antes mostrava categoria de projeto) ---
    por_status = pedidos.values("status").annotate(total=Count("id")).order_by("-total")
    status_labels_map = dict(PedidoMentoria.STATUS_CHOICES)
    grafico_categoria = {
        "labels": [status_labels_map.get(s["status"], s["status"]) for s in por_status],
        "valores": [s["total"] for s in por_status],
    }

    # --- Projetos por estágio ----------------------------------------------
    por_estagio = projetos.values("estagio").annotate(total=Count("id")).order_by("-total")
    estagio_labels_map = dict(Projeto.ESTAGIO_CHOICES)
    grafico_estagio = {
        "labels": [estagio_labels_map.get(e["estagio"], e["estagio"]) for e in por_estagio],
        "valores": [e["total"] for e in por_estagio],
    }

    # --- Mentorias: diagnóstico vs acompanhamento, por ano ------------------
    # (sempre todos os anos, para comparar a evolução)
    mentorias_por_ano_tipo = (
        Mentoria.objects.exclude(data__isnull=True)
        .values("data__year", "tipo")
        .annotate(total=Count("id"))
    )
    anos_mentoria = sorted({m["data__year"] for m in mentorias_por_ano_tipo})
    grafico_mentorias = {
        "labels": [str(a) for a in anos_mentoria],
        "diagnostico": [
            sum(m["total"] for m in mentorias_por_ano_tipo if m["data__year"] == ano and m["tipo"] == "diagnostico")
            for ano in anos_mentoria
        ],
        "acompanhamento": [
            sum(m["total"] for m in mentorias_por_ano_tipo if m["data__year"] == ano and m["tipo"] == "acompanhamento")
            for ano in anos_mentoria
        ],
    }

    # --- Presença em eventos -------------------------------------------------
    # taxa calculada só sobre quem tem presença registrada (presente ou ausente)
    total_inscricoes_evento = inscricoes_eventos.count()
    total_presentes_evento = inscricoes_eventos.filter(presente=True).count()
    total_com_presenca = inscricoes_eventos.exclude(presente__isnull=True).count()
    taxa_presenca = round((total_presentes_evento / total_com_presenca) * 100, 1) if total_com_presenca else None

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
        "total_com_presenca": total_com_presenca,
        "total_pedidos": total_pedidos,
        "pedidos_realizados": pedidos_realizados,
        "taxa_atendimento": taxa_atendimento,
        "grafico_programa_json": json.dumps(grafico_programa),
        "grafico_curso_json": json.dumps(grafico_curso),
        "grafico_tipo_json": json.dumps(grafico_tipo),
        "grafico_categoria_json": json.dumps(grafico_categoria),
        "grafico_estagio_json": json.dumps(grafico_estagio),
        "grafico_mentorias_json": json.dumps(grafico_mentorias),
    }
    return render(request, "dashboard/home.html", contexto)
