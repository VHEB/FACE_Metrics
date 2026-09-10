"""
Popula o catálogo fixo de Programas com os programas atuais do FACE.

Uso:
    python manage.py seed_programas

Rodar de novo é seguro (usa get_or_create pelo slug) — não duplica nem
apaga edições/participações já cadastradas.
"""

from django.core.management.base import BaseCommand

from core.models import Programa, Parceiro

PROGRAMAS = [
    {
        "nome": "Spark",
        "slug": "spark",
        "tipo": "ideacao",
        "descricao": (
            "Programa de ideação do Sebrae para estudantes de graduação "
            "desenvolverem startups digitais, científicas ou de impacto."
        ),
        "parceiros": ["SEBRAE"],
    },
    {
        "nome": "Start",
        "slug": "start",
        "tipo": "pre_aceleracao",
        "descricao": (
            "Pré-aceleração do Sebrae for Startups para startups digitais/deeptechs "
            "com MVP, jornada de 6 meses."
        ),
        "parceiros": ["SEBRAE"],
    },
    {
        "nome": "Internacionalização de Startups",
        "slug": "internacionalizacao-de-startups",
        "tipo": "internacionalizacao",
        "descricao": (
            "Preparação de estudantes, ex-alunos e comunidade externa para o "
            "cenário empreendedor internacional (selo Profissional Cidadão Global)."
        ),
        "parceiros": ["CCBEU", "FCBB"],
    },
    {
        "nome": "CRIE Games",
        "slug": "crie-games",
        "tipo": "evento_capacitacao",
        "descricao": (
            "Iniciativa do SEBRAE-SP para a economia criativa: capacitação, "
            "acesso a mercado e preparação de agentes culturais e empreendedores."
        ),
        "parceiros": ["SEBRAE"],
    },
    {
        "nome": "Power Girl",
        "slug": "power-girl",
        "tipo": "evento_capacitacao",
        "descricao": "Incentivo e capacitação de mulheres no empreendedorismo.",
        "parceiros": ["CCBEU"],
    },
    {
        "nome": "TCC Connect",
        "slug": "tcc-connect",
        "tipo": "inovacao_aberta",
        "descricao": (
            "Atividade de Inovação Aberta que conecta o TCC dos alunos a "
            "problemas reais de empresas parceiras."
        ),
        "parceiros": [],
    },
    {
        "nome": "Programa de Mentoria em Empreendedorismo",
        "slug": "mentoria-em-empreendedorismo",
        "tipo": "mentoria",
        "descricao": (
            "Mentores especialistas (docentes ou parceiros) orientando "
            "projetos e ideias de negócio."
        ),
        "parceiros": [],
    },
    {
        "nome": "Sebrae Aqui",
        "slug": "sebrae-aqui",
        "tipo": "atendimento",
        "descricao": (
            "Atendimento gratuito e especializado a MEIs, micro e pequenas "
            "empresas, com foco em inovação."
        ),
        "parceiros": ["SEBRAE"],
    },
]


class Command(BaseCommand):
    help = "Popula o catálogo fixo de Programas do FACE (idempotente)."

    def handle(self, *args, **options):
        for dados in PROGRAMAS:
            parceiros_nomes = dados.pop("parceiros")
            programa, criado = Programa.objects.get_or_create(
                slug=dados["slug"], defaults=dados,
            )
            for nome_parceiro in parceiros_nomes:
                parceiro, _ = Parceiro.objects.get_or_create(nome=nome_parceiro)
                programa.parceiros.add(parceiro)

            status = "criado" if criado else "já existia"
            self.stdout.write(self.style.SUCCESS(f"Programa '{programa.nome}': {status}"))
