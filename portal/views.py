"""
Views do Portal da Equipe FACE.

Tudo aqui exige login (@login_required) — é a área de uso interno da
equipe, separada do Django Admin. Qualquer pessoa com conta pode criar
Eventos e Mentorias e consultar Pessoas/Projetos; não há distinção de
permissão por enquanto (todo mundo que tem login é equipe de confiança).
"""

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Evento, EventoParticipante, Mentoria, Participacao, Pessoa, Projeto
from .forms import EventoForm, MentoriaForm, PessoaBuscaForm, PessoaQuickForm, ProjetoBuscaForm


@login_required
def home(request):
    return render(request, "portal/home.html")


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@login_required
def evento_list(request):
    eventos = Evento.objects.select_related("parceiro", "edicao").order_by("-data")
    return render(request, "portal/evento_list.html", {"eventos": eventos})


@login_required
def evento_create(request):
    if request.method == "POST":
        form = EventoForm(request.POST)
        if form.is_valid():
            evento = form.save()
            messages.success(request, f'Evento "{evento.nome}" criado com sucesso.')
            return redirect("portal:evento_detail", pk=evento.pk)
    else:
        form = EventoForm()
    return render(request, "portal/evento_form.html", {"form": form, "titulo": "Novo evento"})


@login_required
def evento_edit(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    if request.method == "POST":
        form = EventoForm(request.POST, instance=evento)
        if form.is_valid():
            form.save()
            messages.success(request, "Evento atualizado.")
            return redirect("portal:evento_detail", pk=evento.pk)
    else:
        form = EventoForm(instance=evento)
    return render(request, "portal/evento_form.html", {"form": form, "titulo": f"Editar: {evento.nome}"})


@login_required
def evento_detail(request, pk):
    evento = get_object_or_404(Evento.objects.select_related("parceiro", "edicao"), pk=pk)
    inscricoes = evento.inscricoes.select_related("pessoa").order_by("pessoa__nome")

    if request.method == "POST":
        for inscricao in inscricoes:
            valor = request.POST.get(f"presente_{inscricao.pk}")
            novo_valor = {"sim": True, "nao": False, "": None}.get(valor, None)
            if inscricao.presente != novo_valor:
                inscricao.presente = novo_valor
                inscricao.save(update_fields=["presente"])
        messages.success(request, "Presenças atualizadas.")
        return redirect("portal:evento_detail", pk=evento.pk)

    total = inscricoes.count()
    presentes = inscricoes.filter(presente=True).count()
    return render(request, "portal/evento_detail.html", {
        "evento": evento, "inscricoes": inscricoes, "total": total, "presentes": presentes,
    })


# ---------------------------------------------------------------------------
# Mentorias
# ---------------------------------------------------------------------------

@login_required
def mentoria_list(request):
    mentorias = Mentoria.objects.select_related("edicao", "edicao__programa", "projeto").prefetch_related("mentorados").order_by("-data")
    return render(request, "portal/mentoria_list.html", {"mentorias": mentorias})


@login_required
def mentoria_create(request):
    if request.method == "POST":
        form = MentoriaForm(request.POST)
        if form.is_valid():
            mentoria = form.save()
            messages.success(request, "Mentoria registrada com sucesso.")
            return redirect("portal:mentoria_detail", pk=mentoria.pk)
    else:
        form = MentoriaForm()
    return render(request, "portal/mentoria_form.html", {"form": form, "titulo": "Registrar mentoria"})


@login_required
def mentoria_detail(request, pk):
    mentoria = get_object_or_404(
        Mentoria.objects.select_related("edicao", "edicao__programa", "projeto").prefetch_related("mentorados"), pk=pk,
    )
    return render(request, "portal/mentoria_detail.html", {"mentoria": mentoria})


# ---------------------------------------------------------------------------
# Pessoas
# ---------------------------------------------------------------------------

@login_required
def pessoa_list(request):
    form = PessoaBuscaForm(request.GET or None)
    pessoas = Pessoa.objects.select_related("curso").order_by("nome")

    if form.is_valid():
        termo = form.cleaned_data.get("q")
        tipo = form.cleaned_data.get("tipo_pessoa")
        if termo:
            pessoas = pessoas.filter(
                Q(nome__icontains=termo) | Q(email__icontains=termo) | Q(ra__icontains=termo)
            )
        if tipo:
            pessoas = pessoas.filter(tipo_pessoa=tipo)

    pessoas = pessoas[:200]  # evita carregar uma lista gigante de uma vez
    return render(request, "portal/pessoa_list.html", {"form": form, "pessoas": pessoas})


@login_required
def pessoa_create(request):
    if request.method == "POST":
        form = PessoaQuickForm(request.POST)
        if form.is_valid():
            pessoa = form.save()
            messages.success(request, f'"{pessoa.nome}" cadastrado(a) com sucesso.')
            return redirect("portal:pessoa_detail", pk=pessoa.pk)
    else:
        form = PessoaQuickForm()
    return render(request, "portal/pessoa_form.html", {"form": form})


@login_required
def pessoa_detail(request, pk):
    pessoa = get_object_or_404(Pessoa.objects.select_related("curso"), pk=pk)
    participacoes = (
        Participacao.objects.filter(pessoa=pessoa)
        .select_related("edicao", "edicao__programa")
        .order_by("-edicao__ano")
    )
    mentorias = pessoa.mentorias_recebidas.select_related("edicao", "edicao__programa").order_by("-data")
    projetos = Projeto.objects.filter(integrantes__pessoa=pessoa).distinct()
    eventos = EventoParticipante.objects.filter(pessoa=pessoa).select_related("evento").order_by("-evento__data")

    return render(request, "portal/pessoa_detail.html", {
        "pessoa": pessoa, "participacoes": participacoes, "mentorias": mentorias,
        "projetos": projetos, "eventos": eventos,
    })


# ---------------------------------------------------------------------------
# Projetos
# ---------------------------------------------------------------------------

@login_required
def projeto_list(request):
    form = ProjetoBuscaForm(request.GET or None)
    projetos = Projeto.objects.select_related("empresa_parceira").order_by("nome")

    if form.is_valid():
        termo = form.cleaned_data.get("q")
        categoria = form.cleaned_data.get("categoria")
        estagio = form.cleaned_data.get("estagio")
        if termo:
            projetos = projetos.filter(nome__icontains=termo)
        if categoria:
            projetos = projetos.filter(categoria=categoria)
        if estagio:
            projetos = projetos.filter(estagio=estagio)

    projetos = projetos[:200]
    return render(request, "portal/projeto_list.html", {"form": form, "projetos": projetos})


@login_required
def projeto_detail(request, pk):
    projeto = get_object_or_404(Projeto.objects.select_related("empresa_parceira"), pk=pk)
    integrantes = projeto.integrantes.select_related("pessoa").order_by("pessoa__nome")
    edicoes = projeto.edicoes.select_related("programa").order_by("-ano")
    return render(request, "portal/projeto_detail.html", {
        "projeto": projeto, "integrantes": integrantes, "edicoes": edicoes,
    })
