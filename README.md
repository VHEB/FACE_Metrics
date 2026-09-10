# FACE Metrics

Plataforma de gestão de métricas do FACE — Centro de Empreendedorismo da UniFacens.

## O que já está pronto

- Modelo de dados (`core/models.py`) cobrindo:
  - **Programa** (catálogo fixo: Spark, Start, Internacionalização, CRIE Games,
    Power Girl, TCC Connect, Mentoria, Sebrae Aqui)
  - **Edição** (instância anual/semestral de um Programa — é aqui que entram
    os filtros por ano/semestre para os dashboards)
  - **Pessoa** (aluno, ex-aluno, comunidade externa, docente, colaborador, mentor parceiro)
  - **Participação** (liga Pessoa a uma Edição, com papel e status)
  - **Projeto** (pode atravessar várias Edições) e seus integrantes
  - **Mentoria** e **Evento** (visitas técnicas, palestras etc.)
  - **Parceiro** e **Curso** como catálogos de apoio
- Django Admin já configurado com filtros, busca e inlines úteis
- Comando `seed_programas` para popular o catálogo fixo de Programas

## Setup local

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edite o .env com as credenciais do seu Postgres local

python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_programas   # popula Spark, Start, Power Girl etc.

python manage.py runserver
```

Acesse `http://localhost:8000/admin/` para começar a cadastrar Edições,
Pessoas e Participações pelo Admin enquanto o restante da plataforma não
tem interface própria.

## Próximos passos sugeridos

1. **Rodar localmente e cadastrar dados reais de uma edição** (ex.: Spark 2025.2)
   pelo Admin, pra validar se o modelo cobre bem o que vocês têm hoje.
2. **Dashboards em Python**: com esse modelo, um notebook/script simples com
   `pandas` + `django.db.models` (aggregate, annotate, Count, Q) já dá pra
   gerar as primeiras métricas (participantes por curso, por programa, por
   edição, projetos por estágio etc.). Depois isso pode virar página no
   próprio Django (com `django-plotly-dash`/Chart.js) ou um dashboard à
   parte (Metabase, Superset, Streamlit) apontando pro mesmo Postgres.
3. **Deploy interno**: subir com Gunicorn + Nginx numa VM da rede da
   instituição, Postgres dedicado, `DEBUG=False`, `DJANGO_ALLOWED_HOSTS`
   restrito ao domínio interno.
4. **Fase 2 (API)**: adicionar `djangorestframework` por cima dos mesmos
   models pra alimentar um frontend público (solicitação de mentoria,
   vitrine de programas e viagens).
5. **LGPD**: antes de ir para produção com dados reais de CPF, avaliar
   criptografia em repouso (`django-cryptography` ou `pgcrypto`) e definir
   política de retenção/anonimização.

## Estrutura

```
face_metrics/
├── manage.py
├── requirements.txt
├── .env.example
├── face_metrics/          # configurações do projeto (settings, urls)
└── core/                  # app com os models, admin e seed
    ├── models.py
    ├── admin.py
    └── management/commands/seed_programas.py
```
