"""
Importa a planilha "Agendamento de mentorias" (duas abas):

    - "Respostas ao formulário 1": pedidos de mentoria (intake). Cada linha
      vira uma Pessoa + Projeto (se houver ideia/projeto descrito) +
      Participacao + uma Mentoria tipo="diagnostico" (a triagem inicial que
      pode levar ao programa de Ideação).

    - "Realizadas": mentorias de acompanhamento já realizadas. Cada linha
      vira uma Mentoria tipo="acompanhamento". O mentor (coluna RAE) é
      ignorado de propósito — não é rastreado nesse histórico.

A Edição do programa "Mentoria em Empreendedorismo" é resolvida
automaticamente pelo ANO da data de cada linha (carimbo ou data de
realização), não por um parâmetro fixo — então a planilha pode ter
registros de anos diferentes misturados sem problema.

Uso:
    python manage.py importar_mentorias --arquivo "Agendamento de mentorias.xlsx" --dry-run

    # Quando a aba "Realizadas" ainda não estiver pronta/consolidada:
    python manage.py importar_mentorias --arquivo "Mentorias.xlsx" --pular-realizadas --dry-run
"""

import unicodedata

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Curso, Edicao, Mentoria, Participacao, Programa, Projeto
from core.management.commands._importer_utils import (
    RelatorioImportacao,
    buscar_ou_criar_pessoa,
    carregar_aba_com_cabecalho_flexivel,
    chave_comparacao,
    normalizar_texto,
    truncar_texto,
)

VINCULO_PARA_TIPO_PESSOA = {
    "sou aluno (a)": "aluno",
    "sou aluno": "aluno",
    "sou ex-aluno (a) - alumni": "ex_aluno",
    "sou ex-aluno (a)": "ex_aluno",
    "alumni": "ex_aluno",
    "faco parte da comunidade externa (nao tenho vinculo com a facens)": "comunidade_externa",
    "comunidade externa": "comunidade_externa",
    "colaborador": "colaborador",
    "docente": "docente",
}


def localizar_coluna(df, *pedacos):
    for coluna in df.columns:
        chave = chave_comparacao(coluna)
        if all(chave_comparacao(p) in chave for p in pedacos):
            return coluna
    return None


def localizar_aba(caminho_arquivo, *pedacos):
    """Acha a primeira aba cujo nome normalizado contenha os pedaços dados."""
    xls = pd.ExcelFile(caminho_arquivo)
    for aba in xls.sheet_names:
        chave = chave_comparacao(aba)
        if all(chave_comparacao(p) in chave for p in pedacos):
            return aba
    return None


class CacheEdicoes:
    """Evita bater no banco de novo pra cada linha do mesmo ano."""

    def __init__(self, programa):
        self.programa = programa
        self._cache = {}

    def obter(self, ano):
        if ano not in self._cache:
            self._cache[ano], _ = Edicao.objects.get_or_create(programa=self.programa, ano=ano)
        return self._cache[ano]


class Command(BaseCommand):
    help = "Importa planilha de mentorias (intake + realizadas)."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="Caminho do arquivo .xlsx")
        parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco")
        parser.add_argument(
            "--pular-realizadas", action="store_true",
            help="Processa só a aba de intake/diagnóstico, ignorando a aba Realizadas "
                 "(útil quando ela ainda não estiver consolidada/pronta).",
        )

    def handle(self, *args, **options):
        try:
            programa = Programa.objects.get(slug="mentoria-em-empreendedorismo")
        except Programa.DoesNotExist as exc:
            raise CommandError(
                "Programa 'Mentoria em Empreendedorismo' não encontrado. "
                "Rode 'python manage.py seed_programas' primeiro."
            ) from exc

        try:
            abas_disponiveis = pd.ExcelFile(options["arquivo"]).sheet_names
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {options['arquivo']}") from exc

        pular_realizadas = options["pular_realizadas"]

        aba_intake = localizar_aba(options["arquivo"], "respostas", "formulario")
        aba_realizadas = None if pular_realizadas else localizar_aba(options["arquivo"], "realizada")

        faltando_abas = []
        if not aba_intake:
            faltando_abas.append("intake ('Respostas ao formulário 1')")
        if not pular_realizadas and not aba_realizadas:
            faltando_abas.append("Realizadas")
        if faltando_abas:
            raise CommandError(
                f"Não encontrei a(s) aba(s): {', '.join(faltando_abas)}. "
                f"Abas disponíveis no arquivo: {abas_disponiveis}. "
                f"(Use --pular-realizadas se a aba Realizadas ainda não estiver pronta.)"
            )

        df_intake = carregar_aba_com_cabecalho_flexivel(options["arquivo"], aba_intake)
        df_realizadas = (
            carregar_aba_com_cabecalho_flexivel(options["arquivo"], aba_realizadas)
            if aba_realizadas else None
        )

        relatorio = RelatorioImportacao(self.stdout, self.style)
        dry_run = options["dry_run"]
        cache_edicoes = CacheEdicoes(programa)

        with transaction.atomic():
            self._importar_intake(df_intake, relatorio, cache_edicoes)
            if df_realizadas is not None:
                self._importar_realizadas(df_realizadas, relatorio, cache_edicoes)
            else:
                self.stdout.write(self.style.WARNING("Aba 'Realizadas' pulada (--pular-realizadas)."))

            if dry_run:
                transaction.set_rollback(True)

        relatorio.imprimir_resumo(dry_run)

    # ------------------------------------------------------------------
    def _importar_intake(self, df, relatorio, cache_edicoes):
        col_carimbo = localizar_coluna(df, "carimbo")
        col_nome = localizar_coluna(df, "nome", "complet")
        col_telefone = localizar_coluna(df, "celular")
        col_email = localizar_coluna(df, "mail")
        col_cpf = next((c for c in df.columns if chave_comparacao(c) == "cpf"), None)
        col_ra = next((c for c in df.columns if chave_comparacao(c).rstrip(":") == "ra"), None)
        col_vinculo = localizar_coluna(df, "vinculo", "facens")
        col_curso_aluno = next((c for c in df.columns if chave_comparacao(c) == "curso"), None)
        col_curso_exaluno = localizar_coluna(df, "curso", "fez", "facens")
        col_curso_docente = localizar_coluna(df, "curso", "da aula")
        col_curso_outro = localizar_coluna(df, "outro", "curso")
        col_nome_projeto = localizar_coluna(df, "projeto", "nome")
        col_tematica = localizar_coluna(df, "tematica")
        col_desafio = localizar_coluna(df, "desafio atual")
        col_trl = localizar_coluna(df, "trl")

        for i, linha in df.iterrows():
            numero_linha = i + 3  # header ocupa 2 linhas nessa aba
            nome = normalizar_texto(linha.get(col_nome))
            if not nome:
                relatorio.linha_ignorada(numero_linha, "linha vazia (sem nome)")
                continue

            carimbo = linha.get(col_carimbo)
            if pd.isna(carimbo):
                relatorio.linha_ignorada(numero_linha, f"'{nome}' sem data de envio (carimbo)")
                continue
            data_pedido = carimbo.date() if hasattr(carimbo, "date") else carimbo

            vinculo_chave = chave_comparacao(linha.get(col_vinculo))
            tipo_pessoa = VINCULO_PARA_TIPO_PESSOA.get(vinculo_chave)
            if tipo_pessoa is None:
                relatorio.aviso(f"'{nome}': vínculo não informado/reconhecido — classificado como comunidade_externa.")
                tipo_pessoa = "comunidade_externa"

            nome_curso = ""
            if tipo_pessoa == "aluno" and col_curso_aluno:
                nome_curso = normalizar_texto(linha.get(col_curso_aluno))
            elif tipo_pessoa == "ex_aluno" and col_curso_exaluno:
                nome_curso = normalizar_texto(linha.get(col_curso_exaluno))
            if chave_comparacao(nome_curso) == "outro" and col_curso_outro:
                nome_curso = normalizar_texto(linha.get(col_curso_outro))

            curso = None
            if nome_curso:
                nome_curso = truncar_texto(nome_curso, 150, relatorio, f"curso de {nome}")
                curso, _ = Curso.objects.get_or_create(nome=nome_curso, nivel="graduacao")

            dados_pessoa = {
                "nome": nome,
                "cpf": linha.get(col_cpf) if col_cpf else None,
                "email": linha.get(col_email) if col_email else None,
                "telefone": linha.get(col_telefone) if col_telefone else None,
                "tipo_pessoa": tipo_pessoa,
                "ra": linha.get(col_ra) if col_ra else None,
            }
            pessoa = buscar_ou_criar_pessoa(dados_pessoa, relatorio, curso=curso)

            edicao = cache_edicoes.obter(data_pedido.year)
            Participacao.objects.get_or_create(
                pessoa=pessoa, edicao=edicao, papel="mentorado", defaults={"status": "em_andamento"},
            )

            nome_projeto = normalizar_texto(linha.get(col_nome_projeto)) if col_nome_projeto else ""
            tematica = normalizar_texto(linha.get(col_tematica)) if col_tematica else ""
            desafio = normalizar_texto(linha.get(col_desafio)) if col_desafio else ""
            trl = normalizar_texto(linha.get(col_trl)) if col_trl else ""

            projeto = None
            if nome_projeto or tematica:
                partes_descricao = []
                if tematica:
                    partes_descricao.append(f"Temática: {tematica}")
                if desafio:
                    partes_descricao.append(f"Desafio/motivo da mentoria: {desafio}")
                if trl:
                    partes_descricao.append(f"TRL declarado: {trl}")
                projeto, _ = Projeto.objects.get_or_create(
                    nome=truncar_texto(nome_projeto, 200, relatorio, f"projeto de {nome}") or f"Ideia de {nome}",
                    defaults={"descricao": "\n".join(partes_descricao)},
                )
                projeto.edicoes.add(edicao)

            ja_existe = Mentoria.objects.filter(
                edicao=edicao, tipo="diagnostico", data=data_pedido, mentorados=pessoa,
            ).exists()
            if ja_existe:
                relatorio.aviso(f"Mentoria diagnóstico de '{nome}' em {data_pedido} já importada — pulando duplicata.")
                continue

            mentoria = Mentoria.objects.create(
                tipo="diagnostico", edicao=edicao, projeto=projeto, data=data_pedido,
                tema="Mentoria de diagnóstico (triagem)",
                observacoes=f"Como ficou sabendo: {normalizar_texto(linha.get(localizar_coluna(df, 'ficou sabendo')))}".strip(": "),
            )
            mentoria.mentorados.add(pessoa)

    # ------------------------------------------------------------------
    def _importar_realizadas(self, df, relatorio, cache_edicoes):
        col_nome = next((c for c in df.columns if chave_comparacao(c) == "nome"), None)
        col_telefone = (
            localizar_coluna(df, "telefone") or localizar_coluna(df, "whats") or localizar_coluna(df, "celular")
        )
        col_email = localizar_coluna(df, "mail")
        col_solicitacao = next((c for c in df.columns if chave_comparacao(c) == "solicitacao"), None)
        col_realizacao = next((c for c in df.columns if chave_comparacao(c) == "realizacao"), None)
        col_orientacao = localizar_coluna(df, "orientacao")
        col_observacoes = next((c for c in df.columns if chave_comparacao(c) == "observacoes"), None)
        col_vinculo = localizar_coluna(df, "vinculo")
        col_ra = next((c for c in df.columns if chave_comparacao(c).rstrip(":") == "ra"), None)

        faltando = [n for n, c in [("NOME", col_nome), ("REALIZAÇÃO", col_realizacao)] if c is None]
        if faltando:
            raise CommandError(f"Aba 'Realizadas': não encontrei a(s) coluna(s): {', '.join(faltando)}")

        for i, linha in df.iterrows():
            numero_linha = i + 4  # header ocupa 3 linhas nessa aba
            nome = normalizar_texto(linha.get(col_nome))
            if not nome:
                relatorio.linha_ignorada(numero_linha, "linha vazia (sem nome)")
                continue

            data_sessao = linha.get(col_realizacao)
            if pd.isna(data_sessao):
                relatorio.linha_ignorada(numero_linha, f"'{nome}' sem data de realização")
                continue
            data_sessao = data_sessao.date() if hasattr(data_sessao, "date") else data_sessao

            valor_solicitacao = linha.get(col_solicitacao) if col_solicitacao else None
            nota_data_solicitacao = ""
            if pd.notna(valor_solicitacao) and hasattr(valor_solicitacao, "date"):
                # A coluna SOLICITAÇÃO às vezes traz a data em que o pedido
                # foi feito (em vez do tipo de solicitação) — não é erro,
                # é só um uso inconsistente da mesma coluna. Preservamos a
                # data numa observação em vez de descartar.
                nota_data_solicitacao = f"[Solicitação original em: {valor_solicitacao.date()}]"
                tema = ""
            else:
                tema = normalizar_texto(valor_solicitacao)

            observacoes = " | ".join(
                texto for texto in (
                    nota_data_solicitacao,
                    *(normalizar_texto(linha.get(c)) for c in [col_orientacao, col_observacoes] if c),
                )
                if texto
            )

            tipo_pessoa = "comunidade_externa"
            if col_vinculo:
                tipo_pessoa = VINCULO_PARA_TIPO_PESSOA.get(chave_comparacao(linha.get(col_vinculo)), "comunidade_externa")

            dados_pessoa = {
                "nome": nome,
                "email": linha.get(col_email) if col_email else None,
                "telefone": linha.get(col_telefone) if col_telefone else None,
                "tipo_pessoa": tipo_pessoa,
                "ra": linha.get(col_ra) if col_ra else None,
            }
            pessoa = buscar_ou_criar_pessoa(dados_pessoa, relatorio)

            edicao = cache_edicoes.obter(data_sessao.year)
            Participacao.objects.get_or_create(
                pessoa=pessoa, edicao=edicao, papel="mentorado", defaults={"status": "em_andamento"},
            )

            ja_existe = Mentoria.objects.filter(
                edicao=edicao, tipo="acompanhamento", data=data_sessao, tema=tema,
                observacoes=observacoes, mentorados=pessoa,
            ).exists()
            if ja_existe:
                relatorio.aviso(f"Mentoria de acompanhamento de '{nome}' em {data_sessao} já importada — pulando duplicata.")
                continue

            mentoria = Mentoria.objects.create(
                tipo="acompanhamento", edicao=edicao, data=data_sessao, tema=tema, observacoes=observacoes,
            )
            mentoria.mentorados.add(pessoa)