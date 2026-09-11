"""
Importa a planilha de inscrição do TCC Connect (padrão Google Forms com
ramificação por empresa) e cria:
    - 1 Edição do programa "TCC Connect" (ano/semestre informados)
    - 1 Parceiro por empresa escolhida (STARRET, CPFL, EMICOL...)
    - 1 Projeto por desafio escolhido, ligado à empresa e à Edição
    - 1 Pessoa por líder de grupo (quem respondeu o formulário) + tentativa
      de extrair os demais integrantes do campo de texto livre

As colunas de desafio mudam a cada edição (nomes de empresas/desafios
diferentes ano a ano), então elas são detectadas automaticamente: qualquer
coluna que não seja um campo "fixo" do formulário (nome, RA, e-mail, curso,
empresa, integrantes, dúvidas etc.) é tratada como uma coluna de desafio.

O campo de integrantes do grupo é texto livre e o formato varia bastante.
O parser tenta extrair nome/curso/RA/e-mail de cada bloco; só cria a Pessoa
automaticamente quando encontra RA ou e-mail (confiança alta). Quando não
consegue, reporta no resumo pra cadastro manual — nunca inventa dado.

Uso:
    python manage.py importar_tcc_connect --arquivo "TCC Connect 2025.xlsx" --ano 2025 --dry-run
"""

import re
import unicodedata

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Curso, Edicao, Entrega, Parceiro, Programa, Projeto, ProjetoParticipante, Participacao
from core.management.commands._importer_utils import (
    RelatorioImportacao,
    buscar_ou_criar_pessoa,
    chave_comparacao,
    normalizar_texto,
)

EMAIL_RE = r"[\w\.\+-]+@[\w-]+\.[\w\.-]+"
URL_RE = r"(?:https?://\S+|(?:www\.)?[\w-]+\.(?:com|org|net|br|io|co)(?:\.\w+)?\S*)"


def identificar_colunas_entrega(df):
    return [c for c in df.columns if chave_comparacao(c).startswith("entrega")]

# Colunas "fixas" do formulário — tudo que não bater aqui é tratado como
# coluna de desafio (que varia a cada edição).
META_CHECKS = [
    lambda c: "carimbo" in c,
    lambda c: c.startswith("nome complet"),
    lambda c: c == "ra",
    lambda c: "celular" in c,
    lambda c: "mail" in c,
    lambda c: c == "curso" or "tipo curso" in c,
    lambda c: "nao encontrou" in c or "nao encontrado" in c or ("curso" in c and "campo" in c),
    lambda c: "possui grupo" in c,
    lambda c: "quantas pessoas" in c,
    lambda c: "integrantes" in c,
    lambda c: "duvida" in c,
    lambda c: "empresa" in c,
    lambda c: c.startswith("coluna"),
    lambda c: "video" in c,
    lambda c: c.startswith("entrega"),
]


def eh_coluna_meta(coluna):
    chave = chave_comparacao(coluna)
    return any(checagem(chave) for checagem in META_CHECKS)


def identificar_colunas_desafio(df):
    return [c for c in df.columns if not eh_coluna_meta(c)]


def localizar_coluna(df, *pedacos):
    for coluna in df.columns:
        chave = chave_comparacao(coluna)
        if all(chave_comparacao(p) in chave for p in pedacos):
            return coluna
    return None


def dividir_blocos_integrantes(texto):
    """Separa o texto livre em um bloco por integrante."""
    texto = texto.strip()
    if not texto:
        return []
    blocos = re.split(r"\n\s*\n", texto)
    # Quando o formulário não usa linha em branco entre integrantes mas
    # tem mais de um e-mail no texto, tenta separar linha a linha.
    if len(blocos) == 1 and texto.count("@") > 1:
        blocos = [linha for linha in texto.split("\n") if linha.strip()]
    return [b.strip() for b in blocos if b.strip()]


def parsear_membro(bloco):
    email_match = re.search(EMAIL_RE, bloco)
    email = email_match.group(0) if email_match else None

    ra_match = re.search(r"RA[:\s]*(\d{4,8})", bloco, re.IGNORECASE)
    if not ra_match:
        ra_match = re.search(r"\b(\d{5,7})\b", bloco)
    ra = ra_match.group(1) if ra_match else None

    segmentos = [normalizar_texto(s) for s in re.split(r"[/\n]", bloco) if normalizar_texto(s)]
    nome = segmentos[0] if segmentos else ""
    curso = None
    for seg in segmentos[1:]:
        if "@" in seg or re.fullmatch(r"\d+", seg):
            continue
        curso = seg
        break

    return {"nome": nome, "curso": curso, "ra": ra, "email": email}


class Command(BaseCommand):
    help = "Importa planilha de inscrição do TCC Connect (formato Google Forms)."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="Caminho do arquivo .xlsx")
        parser.add_argument("--ano", required=True, type=int, help="Ano da edição, ex.: 2025")
        parser.add_argument("--semestre", type=int, default=None, help="Semestre da edição (opcional)")
        parser.add_argument("--aba", default=0, help="Nome ou índice da aba (default: primeira)")
        parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco")

    def handle(self, *args, **options):
        try:
            programa = Programa.objects.get(slug="tcc-connect")
        except Programa.DoesNotExist as exc:
            raise CommandError(
                "Programa 'TCC Connect' não encontrado. Rode 'python manage.py seed_programas' primeiro."
            ) from exc

        try:
            df = pd.read_excel(options["arquivo"], sheet_name=options["aba"])
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {options['arquivo']}") from exc

        col_nome = localizar_coluna(df, "nome", "complet")
        col_ra = next((c for c in df.columns if chave_comparacao(c) == "ra"), None)
        col_celular = localizar_coluna(df, "celular")
        col_email = localizar_coluna(df, "mail")
        col_curso = next((c for c in df.columns if chave_comparacao(c) == "curso"), None)
        col_tipo_curso = localizar_coluna(df, "tipo curso")
        col_empresa = localizar_coluna(df, "empresa")
        col_integrantes = localizar_coluna(df, "integrantes")
        colunas_desafio = identificar_colunas_desafio(df)
        colunas_entrega = identificar_colunas_entrega(df)

        faltando = [
            nome for nome, col in
            [("Nome", col_nome), ("Empresa", col_empresa)] if col is None
        ]
        if faltando:
            raise CommandError(
                f"Não encontrei a(s) coluna(s) obrigatória(s): {', '.join(faltando)}. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

        self.stdout.write(f"Colunas de desafio detectadas ({len(colunas_desafio)}): {colunas_desafio}")
        self.stdout.write(f"Colunas de entrega detectadas ({len(colunas_entrega)}): {colunas_entrega}")

        relatorio = RelatorioImportacao(self.stdout, self.style)
        dry_run = options["dry_run"]

        with transaction.atomic():
            edicao, edicao_criada = Edicao.objects.get_or_create(
                programa=programa, ano=options["ano"], semestre=options["semestre"],
            )
            self.stdout.write(
                self.style.SUCCESS(f"Edição {'criada' if edicao_criada else 'reaproveitada'}: {edicao}")
            )

            for i, linha in df.iterrows():
                numero_linha = i + 2
                nome = normalizar_texto(linha.get(col_nome))
                if not nome:
                    relatorio.linha_ignorada(numero_linha, "sem nome preenchido")
                    continue

                nome_curso = normalizar_texto(linha.get(col_curso)) if col_curso else ""
                nivel_curso = "graduacao"
                if col_tipo_curso:
                    tipo_valor = chave_comparacao(linha.get(col_tipo_curso))
                    if "pos" in tipo_valor:
                        nivel_curso = "pos"
                curso = None
                if nome_curso:
                    curso, _ = Curso.objects.get_or_create(nome=nome_curso, nivel=nivel_curso)

                nome_empresa = normalizar_texto(linha.get(col_empresa))
                parceiro = None
                if nome_empresa:
                    parceiro, _ = Parceiro.objects.get_or_create(nome=nome_empresa)

                dados_pessoa = {
                    "nome": nome,
                    "email": linha.get(col_email) if col_email else None,
                    "telefone": linha.get(col_celular) if col_celular else None,
                    "tipo_pessoa": "aluno",
                    "ra": linha.get(col_ra) if col_ra else None,
                }
                pessoa = buscar_ou_criar_pessoa(dados_pessoa, relatorio, curso=curso)

                participacao, _ = Participacao.objects.get_or_create(
                    pessoa=pessoa, edicao=edicao, papel="participante",
                    defaults={"status": "em_andamento"},
                )

                # --- desafio(s) escolhido(s) ---
                projetos_da_linha = []
                desafios_preenchidos = [
                    c for c in colunas_desafio
                    if normalizar_texto(linha.get(c))
                ]
                if desafios_preenchidos:
                    for col_desafio in desafios_preenchidos:
                        descricao = normalizar_texto(linha.get(col_desafio))
                        projeto, _ = Projeto.objects.get_or_create(
                            nome=normalizar_texto(col_desafio),
                            defaults={
                                "descricao": descricao,
                                "area": nome_empresa,
                                "empresa_parceira": parceiro,
                            },
                        )
                        projeto.edicoes.add(edicao)
                        ProjetoParticipante.objects.get_or_create(
                            projeto=projeto, pessoa=pessoa, defaults={"papel": "fundador"},
                        )
                        projetos_da_linha.append(projeto)
                elif nome_empresa:
                    # Escolheu empresa mas o formulário não chegou a
                    # capturar um desafio específico ainda.
                    projeto, criado = Projeto.objects.get_or_create(
                        nome=f"{nome_empresa} — desafio a definir",
                        defaults={"area": nome_empresa, "empresa_parceira": parceiro},
                    )
                    projeto.edicoes.add(edicao)
                    ProjetoParticipante.objects.get_or_create(
                        projeto=projeto, pessoa=pessoa, defaults={"papel": "fundador"},
                    )
                    projetos_da_linha.append(projeto)
                    relatorio.aviso(
                        f"{nome} escolheu '{nome_empresa}' mas não tem desafio específico "
                        f"selecionado na planilha — revisar e renomear o projeto manualmente."
                    )

                # --- entregas (vídeos, TCC final etc.) ---
                for col_entrega in colunas_entrega:
                    valor = normalizar_texto(linha.get(col_entrega))
                    if not valor:
                        continue
                    url_match = re.search(URL_RE, valor)
                    Entrega.objects.get_or_create(
                        participacao=participacao,
                        nome=normalizar_texto(col_entrega),
                        defaults={
                            "projeto": projetos_da_linha[0] if projetos_da_linha else None,
                            "tipo": "video" if url_match else "outro",
                            "status": "entregue",
                            "link": url_match.group(0) if url_match else "",
                        },
                    )
                    if not url_match:
                        relatorio.aviso(
                            f"'{col_entrega}' de {nome} não parece um link — conferir manualmente: \"{valor}\""
                        )

                # --- integrantes do grupo (texto livre) ---
                texto_integrantes = normalizar_texto(linha.get(col_integrantes)) if col_integrantes else ""
                for bloco in dividir_blocos_integrantes(texto_integrantes):
                    membro = parsear_membro(bloco)
                    if not membro["nome"]:
                        continue
                    if not (membro["ra"] or membro["email"]):
                        relatorio.aviso(
                            f"Integrante de grupo não identificado com confiança (linha {numero_linha}, "
                            f"grupo de {nome}): \"{bloco}\" — cadastre manualmente se necessário."
                        )
                        continue

                    curso_membro = None
                    if membro["curso"]:
                        curso_membro, _ = Curso.objects.get_or_create(nome=membro["curso"], nivel="graduacao")

                    pessoa_membro = buscar_ou_criar_pessoa(
                        {
                            "nome": membro["nome"],
                            "email": membro["email"],
                            "ra": membro["ra"],
                            "tipo_pessoa": "aluno",
                        },
                        relatorio,
                        curso=curso_membro,
                    )
                    Participacao.objects.get_or_create(
                        pessoa=pessoa_membro, edicao=edicao, papel="participante",
                        defaults={"status": "em_andamento"},
                    )
                    for projeto in projetos_da_linha:
                        ProjetoParticipante.objects.get_or_create(
                            projeto=projeto, pessoa=pessoa_membro, defaults={"papel": "colaborador"},
                        )

            if dry_run:
                transaction.set_rollback(True)

        relatorio.imprimir_resumo(dry_run)
