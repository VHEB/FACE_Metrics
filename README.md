# FACE Metrics

Plataforma de gestão de métricas do FACE — Centro de Empreendedorismo da UniFacens.

## O que já está pronto

- Modelo de dados (`core/models.py`):
  - **Programa** (catálogo fixo) → **Edição** (ex.: TCC Connect 2025.1) → **Participação**
    (papel: participante, líder, integrante...; status: inscrito, participou, concluído, desistente...)
  - **Pessoa**: cadastro único. CPF validado (dígitos verificadores) e único; vínculo atual + vínculo de
    cada inscrição/pedido (o vínculo muda com o tempo)
  - **Pedido de mentoria**: o pedido do formulário, com status de atendimento (para agendar, agendado,
    realizado, não respondeu...)
  - **Mentoria**: a SESSÃO realizada, ligada ao pedido (1ª sessão = diagnóstico), com orientação e
    encaminhamentos (WF, Spark, Start...)
  - **Evento**: viagens/missões, palestras, visitas técnicas — com inscrição, status e presença
  - **Projeto** (TRL inicial/atual, status, empresa parceira) e integrantes; **Mentor** (perfil)
- **Portal da equipe** (`/portal/`): pedidos de mentoria (filtros, status, responsável), sessões,
  pessoas, projetos, viagens e eventos (com marcação de presença)
- **Dashboard** (`/dashboard/`): todos os números respeitam o filtro de ano
- **Admin** (`/admin/`) para manutenção
- Carga das planilhas: `consolidacao/` (fora deste app) gera a base consolidada e o comando
  `carregar_base_consolidada` a coloca no banco (com simulação, backup e desfazer)

## Carregar os dados das planilhas

```powershell
# 1. consolidar as planilhas (gera dados\saida\base_consolidada_face.json)
python -X utf8 consolidacao\consolidar.py dados\planilhas --saida dados\saida --base-antiga dados\face_dados.json
# 2. simular a carga (não altera nada)
python -X utf8 manage.py carregar_base_consolidada dados\saida\base_consolidada_face.json
# 3. carregar de verdade (faz backup em backups\ antes)
python -X utf8 manage.py carregar_base_consolidada dados\saida\base_consolidada_face.json --confirmar
# desfazer: volta ao backup indicado no fim da carga
python -X utf8 manage.py carregar_base_consolidada --restaurar backups\antes_da_carga_....json --confirmar
```

Testes: `python manage.py test core`

## Setup local

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edite o .env com as credenciais do seu Postgres local

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
