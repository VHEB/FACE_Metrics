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
            pessoa.telefone = normalizar_texto(dados.get("telefone"))
            mudou = True
        if not pessoa.ra and dados.get("ra"):
            pessoa.ra = normalizar_texto(dados.get("ra"))
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
        rg=rg or "",
        email=email,
        telefone=normalizar_texto(dados.get("telefone")),
        tipo_pessoa=dados.get("tipo_pessoa") or "comunidade_externa",
        curso=curso,
        ra=normalizar_texto(dados.get("ra")),
        cidade=normalizar_texto(dados.get("cidade")),
        semestre_ingresso=normalizar_texto(dados.get("semestre_ingresso")),
    )
    pessoa.save()
    relatorio.pessoa_criada()
    return pessoa
