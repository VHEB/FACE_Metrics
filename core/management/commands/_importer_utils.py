"""
Utilitários compartilhados pelos comandos `importar_*`.

Regra de deduplicação de Pessoa (nessa ordem de prioridade):
    1. CPF (se ambos os lados tiverem)
    2. RG (se ambos os lados tiverem)
    3. E-mail (case-insensitive)
    4. Nome + Curso (fallback fraco — é reportado como "possível duplicata"
       para revisão manual, nunca mesclado às cegas)

Este módulo tem prefixo "_" no nome do arquivo (`_importer_utils.py`) de
propósito: comandos do Django management são todo arquivo .py dentro de
`management/commands/`, então um nome começando com "_" evita que o Django
tente registrá-lo como comando.
"""

import re
import unicodedata

import pandas as pd

from core.models import Pessoa


def normalizar_documento(valor):
    """Remove tudo que não é dígito. Retorna None se vazio."""
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    return digitos or None


def normalizar_texto(valor):
    """Trim + colapsa espaços duplos. Retorna '' para valores vazios/NaN."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.lower() in ("nan", "none", "nat"):
        return ""
    return re.sub(r"\s+", " ", texto)


def chave_comparacao(texto):
    """Normaliza texto pra comparação tolerante a acento/maiúsculas."""
    texto = normalizar_texto(texto).lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto


class RelatorioImportacao:
    """Acumula estatísticas e mensagens durante uma importação, pra imprimir um resumo no final."""

    def __init__(self, stdout, style):
        self.stdout = stdout
        self.style = style
        self.pessoas_criadas = 0
        self.pessoas_encontradas = 0
        self.linhas_ignoradas = []
        self.duplicatas_suspeitas = []
        self.avisos = []

    def pessoa_criada(self):
        self.pessoas_criadas += 1

    def pessoa_encontrada(self):
        self.pessoas_encontradas += 1

    def linha_ignorada(self, numero_linha, motivo):
        self.linhas_ignoradas.append((numero_linha, motivo))

    def duplicata_suspeita(self, pessoa, dados_linha):
        self.duplicatas_suspeitas.append((pessoa, dados_linha))

    def aviso(self, texto):
        self.avisos.append(texto)

    def imprimir_resumo(self, dry_run):
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING("== Resumo da importação =="))
        if dry_run:
            w(self.style.WARNING("MODO DRY-RUN: nada foi gravado no banco."))
        w(f"Pessoas criadas:   {self.pessoas_criadas}")
        w(f"Pessoas já existiam (matched): {self.pessoas_encontradas}")
        w(f"Linhas ignoradas:  {len(self.linhas_ignoradas)}")
        for numero, motivo in self.linhas_ignoradas:
            w(f"   - linha {numero}: {motivo}")
        w(f"Possíveis duplicatas (revisar manualmente): {len(self.duplicatas_suspeitas)}")
        for pessoa, dados in self.duplicatas_suspeitas:
            w(f"   - '{dados.get('nome')}' pode já existir como '{pessoa.nome}' (id={pessoa.pk}) — matched só por nome+curso")
        if self.avisos:
            w(f"Avisos: {len(self.avisos)}")
            for aviso in self.avisos:
                w(f"   - {aviso}")


def truncar_texto(valor, tamanho, relatorio=None, contexto=""):
    """Versão genérica de truncar_para_campo, pra usar em qualquer CharField (não só Pessoa)."""
    if not valor or len(valor) <= tamanho:
        return valor
    if relatorio is not None:
        relatorio.aviso(
            f"Valor de {contexto or 'um campo'} excedia {tamanho} caracteres e foi cortado: "
            f"\"{valor}\" -> \"{valor[:tamanho]}\""
        )
    return valor[:tamanho]


def truncar_para_campo(nome_campo, valor, relatorio=None, contexto=""):
    """Corta o valor pro max_length real do campo no model Pessoa, avisando se precisou cortar."""
    if not valor:
        return valor
    max_len = Pessoa._meta.get_field(nome_campo).max_length
    if max_len and len(valor) > max_len:
        if relatorio is not None:
            relatorio.aviso(
                f"Campo '{nome_campo}' de {contexto or 'um registro'} excedia {max_len} caracteres "
                f"e foi cortado: \"{valor}\" -> \"{valor[:max_len]}\""
            )
        return valor[:max_len]
    return valor


def carregar_aba_com_cabecalho_flexivel(caminho_arquivo, nome_aba):
    """
    Lê uma aba detectando automaticamente onde está o cabeçalho, em vez de
    assumir uma posição fixa (header=N). Lida com dois formatos vistos na
    prática:
        - cabeçalho numa linha só (ex.: planilha de 2026)
        - cabeçalho em duas linhas, com uma linha "pai" (ex.: "DATAS") que
          se divide em sub-colunas na linha seguinte (ex.: "SOLICITAÇÃO" /
          "REALIZAÇÃO"), como na planilha de 2024/2025.
    """
    bruto = pd.read_excel(caminho_arquivo, sheet_name=nome_aba, header=None)

    linha_cabecalho = None
    for i in range(min(10, len(bruto))):
        valores = {chave_comparacao(v) for v in bruto.iloc[i] if pd.notna(v)}
        if any("nome" in v for v in valores):
            linha_cabecalho = i
            break
    if linha_cabecalho is None:
        raise ValueError(f"Não encontrei uma linha de cabeçalho com 'Nome' na aba '{nome_aba}'.")

    cabecalho = bruto.iloc[linha_cabecalho]
    proxima = bruto.iloc[linha_cabecalho + 1] if linha_cabecalho + 1 < len(bruto) else None

    tem_subcabecalho = False
    if proxima is not None:
        total_colunas = bruto.shape[1]
        preenchidas_proxima = [j for j in range(total_colunas) if pd.notna(proxima[j])]
        preenche_lacuna = sum(1 for j in preenchidas_proxima if pd.isna(cabecalho[j]))
        sobrepoe_rotulo = sum(1 for j in preenchidas_proxima if pd.notna(cabecalho[j]))
        # Só tratamos como sub-cabeçalho (não como primeira linha de dados de
        # verdade) quando a linha de baixo preenche principalmente lacunas
        # do cabeçalho (rótulo "pai" mesclado, tipo "DATAS" -> "SOLICITAÇÃO"/
        # "REALIZAÇÃO") e cobre só uma minoria das colunas — uma linha de
        # dados real, mesmo esparsa, tende a sobrepor rótulos já existentes
        # (ex.: a própria coluna "Nome" sempre vem preenchida).
        if preenchidas_proxima and len(preenchidas_proxima) < total_colunas * 0.5 and preenche_lacuna >= sobrepoe_rotulo:
            tem_subcabecalho = True

    colunas = []
    sub = proxima if tem_subcabecalho else None
    for j in range(bruto.shape[1]):
        valor_sub = sub[j] if sub is not None else None
        valor_principal = cabecalho[j]
        if pd.notna(valor_sub):
            colunas.append(normalizar_texto(valor_sub))
        elif pd.notna(valor_principal):
            colunas.append(normalizar_texto(valor_principal))
        else:
            colunas.append(f"coluna_{j}")

    inicio_dados = linha_cabecalho + (2 if tem_subcabecalho else 1)
    dados = bruto.iloc[inicio_dados:].reset_index(drop=True)
    dados.columns = colunas
    return dados


def buscar_ou_criar_pessoa(dados, relatorio, curso=None):
    """
    dados: dict com chaves possíveis: nome, cpf, rg, email, telefone,
           tipo_pessoa, ra, cidade, semestre_ingresso
    curso: instância de Curso ou None
    Retorna a instância de Pessoa (nova ou existente).
    """
    nome = normalizar_texto(dados.get("nome"))
    cpf = normalizar_documento(dados.get("cpf"))
    rg = normalizar_documento(dados.get("rg"))
    email = normalizar_texto(dados.get("email")).lower()

    pessoa = None

    if cpf:
        pessoa = Pessoa.objects.filter(cpf=cpf).first()
    if pessoa is None and rg:
        pessoa = Pessoa.objects.filter(rg=rg).first()
    if pessoa is None and email:
        pessoa = Pessoa.objects.filter(email__iexact=email).first()

    duplicata_fraca = False
    if pessoa is None:
        # Fallback fraco: nome + curso. Não confiamos cegamente —
        # só reaproveita se encontrar, mas sinaliza pra revisão.
        candidatos = Pessoa.objects.filter(nome__iexact=nome)
        if curso is not None:
            candidatos = candidatos.filter(curso=curso)
        pessoa = candidatos.first()
        if pessoa is not None:
            duplicata_fraca = True

    if pessoa is not None:
        relatorio.pessoa_encontrada()
        if duplicata_fraca:
            relatorio.duplicata_suspeita(pessoa, dados)
        # Preenche campos que a pessoa ainda não tinha (nunca sobrescreve o que já existe).
        mudou = False
        if not pessoa.cpf and cpf:
            pessoa.cpf = cpf
            mudou = True
        if not pessoa.rg and rg:
            pessoa.rg = rg
            mudou = True
        if not pessoa.email and email:
            pessoa.email = email
            mudou = True
        if not pessoa.telefone and dados.get("telefone"):
            pessoa.telefone = truncar_para_campo(
                "telefone", normalizar_texto(dados.get("telefone")), relatorio, nome
            )
            mudou = True
        if not pessoa.ra and dados.get("ra"):
            pessoa.ra = truncar_para_campo("ra", normalizar_texto(dados.get("ra")), relatorio, nome)
            mudou = True
        if curso is not None and pessoa.curso is None:
            pessoa.curso = curso
            mudou = True
        if mudou:
            pessoa.save()
        return pessoa

    pessoa = Pessoa(
        nome=nome,
        cpf=cpf,
        rg=truncar_para_campo("rg", rg or "", relatorio, nome),
        email=email,
        telefone=truncar_para_campo("telefone", normalizar_texto(dados.get("telefone")), relatorio, nome),
        tipo_pessoa=dados.get("tipo_pessoa") or "comunidade_externa",
        curso=curso,
        ra=truncar_para_campo("ra", normalizar_texto(dados.get("ra")), relatorio, nome),
        cidade=truncar_para_campo("cidade", normalizar_texto(dados.get("cidade")), relatorio, nome),
        semestre_ingresso=truncar_para_campo(
            "semestre_ingresso", normalizar_texto(dados.get("semestre_ingresso")), relatorio, nome
        ),
    )
    pessoa.save()
    relatorio.pessoa_criada()
    return pessoa
