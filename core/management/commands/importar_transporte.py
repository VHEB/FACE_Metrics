"""
Importa uma planilha de inscrição de transporte/evento (padrão Google Forms
como a do "Transporte SciBiz") e cria:
    - 1 Evento (se ainda não existir, pelo nome + data)
    - 1 Pessoa por linha (reaproveitando se já existir — ver _importer_utils)
    - o vínculo Pessoa <-> Evento (participantes)

Uso:
    python manage.py importar_transporte \\
        --arquivo "Transporte - SciBiz - 9ª edição (respostas).xlsx" \\
        --evento-nome "SciBiz - 9ª edição" \\
        --data 2026-05-15 \\
        --local "São Paulo, SP" \\
        --tipo feira \\
        --dry-run

Rode sempre primeiro com --dry-run pra conferir o resumo antes de gravar de verdade.
"""

import datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Curso, Evento, EventoParticipante
from core.management.commands._importer_utils import (
    RelatorioImportacao,
    buscar_ou_criar_pessoa,
    chave_comparacao,
    normalizar_texto,
)

VINCULO_PARA_TIPO_PESSOA = {
    "aluno de graduacao": "aluno",
    "aluno de graduaçao": "aluno",
    "aluno de pos graduacao": "aluno",
    "alumni": "ex_aluno",
    "ex-aluno": "ex_aluno",
    "colaborador": "colaborador",
    "docente": "docente",
    "professor": "docente",
    "comunidade externa": "comunidade_externa",
}


def mapear_tipo_pessoa(valor_vinculo, relatorio, nome_pessoa):
    chave = chave_comparacao(valor_vinculo)
    if chave in VINCULO_PARA_TIPO_PESSOA:
        return VINCULO_PARA_TIPO_PESSOA[chave]
    # Fallback pra valores que não batem exatamente (ex.: "Irmão de Aluna (Graduação)")
    relatorio.aviso(
        f"Vínculo '{valor_vinculo}' (linha de {nome_pessoa}) não reconhecido — "
        f"classificado como 'comunidade_externa'. Ajuste manualmente se necessário."
    )
    return "comunidade_externa"


def localizar_coluna(df, *pedacos):
    """Acha a primeira coluna cujo nome normalizado contenha todos os pedaços dados."""
    for coluna in df.columns:
        chave = chave_comparacao(coluna)
        if all(chave_comparacao(p) in chave for p in pedacos):
            return coluna
    return None


class Command(BaseCommand):
    help = "Importa planilha de inscrição de transporte/evento (formato Google Forms)."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="Caminho do arquivo .xlsx")
        parser.add_argument("--evento-nome", required=True, help='Ex.: "SciBiz - 9ª edição"')
        parser.add_argument("--data", required=True, help="Data do evento, formato AAAA-MM-DD")
        parser.add_argument("--local", default="", help="Local do evento (opcional)")
        parser.add_argument(
            "--tipo", default="feira", choices=[c for c, _ in Evento.TIPO_CHOICES],
            help="Tipo do evento (default: feira)",
        )
        parser.add_argument("--aba", default=0, help="Nome ou índice da aba da planilha (default: primeira)")
        parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco")

    def handle(self, *args, **options):
        try:
            data_evento = datetime.datetime.strptime(options["data"], "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError("Formato de --data inválido. Use AAAA-MM-DD, ex.: 2026-05-15.") from exc

        try:
            df = pd.read_excel(options["arquivo"], sheet_name=options["aba"])
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {options['arquivo']}") from exc

        col_nome = localizar_coluna(df, "nome")
        col_rg = localizar_coluna(df, "rg")
        col_email = localizar_coluna(df, "mail")
        col_telefone = localizar_coluna(df, "whatsapp") or localizar_coluna(df, "telefone") or localizar_coluna(df, "celular")
        col_vinculo = localizar_coluna(df, "vinculo")
        col_curso = localizar_coluna(df, "curso") and next(
            (c for c in df.columns if chave_comparacao(c) == "curso"), None
        )
        col_curso_outro = localizar_coluna(df, "outro", "curso")
        col_ra = next((c for c in df.columns if chave_comparacao(c) == "ra"), None)
        col_duvidas = localizar_coluna(df, "duvida")

        faltando = [
            nome for nome, col in [("Nome", col_nome), ("Vínculo", col_vinculo)] if col is None
        ]
        if faltando:
            raise CommandError(
                f"Não encontrei a(s) coluna(s) obrigatória(s) na planilha: {', '.join(faltando)}. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

        relatorio = RelatorioImportacao(self.stdout, self.style)
        dry_run = options["dry_run"]

        with transaction.atomic():
            evento, evento_criado = Evento.objects.get_or_create(
                nome=options["evento_nome"],
                data=data_evento,
                defaults={"tipo": options["tipo"], "local": options["local"]},
            )
            if evento_criado:
                self.stdout.write(self.style.SUCCESS(f"Evento criado: {evento}"))
            else:
                self.stdout.write(f"Evento já existia, reaproveitando: {evento}")

            for i, linha in df.iterrows():
                numero_linha = i + 2  # +2: cabeçalho ocupa a linha 1, e i é 0-indexed

                nome = normalizar_texto(linha.get(col_nome))
                if not nome:
                    relatorio.linha_ignorada(numero_linha, "sem nome preenchido")
                    continue

                vinculo_valor = linha.get(col_vinculo)
                tipo_pessoa = mapear_tipo_pessoa(vinculo_valor, relatorio, nome)

                nome_curso = normalizar_texto(linha.get(col_curso)) if col_curso else ""
                if chave_comparacao(nome_curso) == "outro" and col_curso_outro:
                    nome_curso = normalizar_texto(linha.get(col_curso_outro))

                curso = None
                if nome_curso:
                    curso, _ = Curso.objects.get_or_create(nome=nome_curso, nivel="graduacao")

                dados_pessoa = {
                    "nome": nome,
                    "rg": linha.get(col_rg) if col_rg else None,
                    "email": linha.get(col_email) if col_email else None,
                    "telefone": linha.get(col_telefone) if col_telefone else None,
                    "tipo_pessoa": tipo_pessoa,
                    "ra": linha.get(col_ra) if col_ra else None,
                }
                pessoa = buscar_ou_criar_pessoa(dados_pessoa, relatorio, curso=curso)
                EventoParticipante.objects.get_or_create(evento=evento, pessoa=pessoa)

                if col_duvidas:
                    duvida = normalizar_texto(linha.get(col_duvidas))
                    if duvida:
                        relatorio.aviso(f"Dúvida registrada por {nome}: \"{duvida}\" (não há campo pra isso — só ficou no log)")

            if dry_run:
                transaction.set_rollback(True)

        relatorio.imprimir_resumo(dry_run)
