# Consolidação das planilhas do FACE

Lê todas as planilhas do Google Forms do FACE (mentorias, extensão, programas,
viagens e eventos) e gera uma base única e padronizada. As planilhas originais
nunca são alteradas.

## Como rodar

Requisitos: Python 3.10+ e `openpyxl` (`pip install openpyxl`).

1. Baixe as planilhas do Google Forms (.xlsx) numa pasta, por exemplo `planilhas/`.
   Os nomes podem ser os originais: o script reconhece cada uma pelo nome.
2. Na pasta destes scripts:

```powershell
python -X utf8 consolidar.py planilhas --saida saida --base-antiga face_dados.json
```

`--base-antiga` é opcional. Serve para trazer a presença do SciBiz, que foi marcada
à mão no sistema antigo e não existe em nenhuma planilha.

Coloque o `decisoes_revisao.json` **na mesma pasta das planilhas**: ele é lido
automaticamente (ou indique outro caminho com `--decisoes`).

## Ciclo de revisão

1. Rode o `consolidar.py` → sai a `revisao_consolidacao_face.xlsx` só com o que ainda não foi decidido.
2. A equipe preenche as colunas amarelas (sem apagar colunas: há uma coluna oculta que identifica cada linha).
3. Importe as respostas:

```powershell
python -X utf8 importar_revisao.py revisao_consolidacao_face.xlsx --decisoes planilhas\decisoes_revisao.json
```

4. Rode o `consolidar.py` de novo. As decisões ficam guardadas e valem para sempre,
   inclusive quando entram planilhas novas.

Datas, locais e o significado das cores **não** vão para o JSON: o `importar_revisao.py`
mostra essas respostas na tela para serem copiadas para o `catalogo.py`.

## O que sai

| Arquivo | Conteúdo |
|---|---|
| `base_consolidada_face.xlsx` | Resumo com métricas por ano + uma aba por tabela |
| `base_consolidada_face.json` | As mesmas tabelas, para carregar na nova plataforma |
| `revisao_consolidacao_face.xlsx` | O que precisa de confirmação da equipe |

Tabelas: Pessoas, Atividades, Inscrições, Projetos, Integrantes, Pedidos de mentoria,
Sessões de mentoria, Mentores.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `catalogo.py` | Planilhas, atividades, datas, locais e significado das cores. **Edite aqui** para incluir uma planilha nova |
| `importar_revisao.py` | Lê a planilha de revisão preenchida e atualiza o `decisoes_revisao.json` |
| `decisoes.py` | Aplica as decisões da equipe na consolidação |
| `normalizar.py` | Regras de padronização (cursos, telefones, CPF, TRL, categorias) |
| `fontes.py` | Leitores de cada tipo de formulário |
| `consolidar.py` | Unificação de pessoas e projetos, ligação pedido ↔ sessão, métricas |
| `saidas.py` | Gravação do Excel e do JSON |

## Regras principais

- **Pessoa única**: une registros por CPF → e-mail → RG → RA → telefone + primeiro
  nome → nome completo (3+ palavras). Nunca une quando CPF ou RA se contradizem.
  Uniões mais fracas vão para a planilha de revisão.
- **CPF ausente não é erro** (passou a ser pedido em meados de 2025).
- **Vínculo é guardado em cada inscrição/pedido**, porque muda com o tempo
  (aluno em 2023, ex-aluno em 2026). A pessoa fica com o vínculo mais recente.
- **Status dos pedidos de mentoria vem das cores** que a equipe usa na planilha
  (legenda: Realizado, Não realizado, Agendado...). Se houver sessão registrada na
  aba "Realizadas", o pedido conta como realizado.
- **Sessões** são ligadas ao pedido mais recente da mesma pessoa feito antes da sessão.
- **Projeto só existe quando há um nome de verdade.** Respostas como "Não", "Ainda não
  tem nome" não viram projeto; a temática continua guardada no pedido.
- **Cursos**: as turmas da extensão ("- Projeto Startup", "- Gestão da Inovação")
  ficam em "Turma da extensão" e o curso fica limpo.

## LGPD

As saídas e o `decisoes_revisao.json` contêm dados pessoais. Não versione no Git:
inclua `saida/`, `*.xlsx` e `*.json` no `.gitignore`.
