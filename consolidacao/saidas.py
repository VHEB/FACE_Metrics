"""Gravação das saídas (Excel e JSON)."""

import json
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

AZUL = "1F3864"
CAB = PatternFill("solid", start_color=AZUL)
AMARELO = PatternFill("solid", start_color="FFF2CC")
LISTRA = PatternFill("solid", start_color="F3F6FA")
FINA = Border(bottom=Side(style="thin", color="D0D7E2"))

ROTULOS = {
    "id": "ID", "cpf": "CPF", "ra": "RA", "rg": "RG", "cep": "CEP", "cnpj": "CNPJ", "trl": "TRL", "ods": "ODS",
    "email": "E-mail", "emails_alternativos": "Outros e-mails", "consentimento_lgpd": "Consentimento LGPD",
    "pessoa_id": "ID pessoa", "projeto_id": "ID projeto", "pedido_id": "ID pedido", "atividade_id": "ID atividade",
    "trl_inicial": "TRL inicial", "trl_atual": "TRL atual", "nivel": "Nível",
    "vinculo_atual": "Vínculo atual", "vinculos_declarados": "Vínculos já declarados",
    "inscricoes": "Inscrições", "sessoes_mentoria": "Sessões de mentoria", "pedidos_mentoria": "Pedidos de mentoria",
    "data_inscricao": "Data de inscrição", "edicao": "Edição", "descricao": "Descrição", "observacao": "Observação",
    "observacoes": "Observações", "orientacao": "Orientação / próximos passos", "area": "Área",
    "tematica": "Temática", "periodo": "Período", "horario": "Horário", "sessoes_registradas": "Sessões registradas",
    "dias_ate_primeira_sessao": "Dias até a 1ª sessão", "data_primeira_sessao": "Data da 1ª sessão",
    "vinculo_no_pedido": "Vínculo no pedido", "curso_no_pedido": "Curso no pedido",
    "vinculo_na_inscricao": "Vínculo na inscrição", "curso_na_inscricao": "Curso na inscrição",
    "turma_extensao": "Turma da extensão", "marcacao_cor": "Marcação (cor)", "status_planilha": "Status na planilha",
    "marcada_2023": "Marcada? (2023)", "formularios_enviados": "Formulários enviados",
    "projeto_facens": "Ligado a projeto Facens", "projeto_facens_texto": "Ligado a projeto Facens (resposta)",
    "como_soube": "Como soube", "como_soube_texto": "Como soube (resposta)", "formato_texto": "Formato (resposta)",
    "nome_projeto_informado": "Nome do projeto (resposta)", "horario_alternativo": "Horário alternativo",
    "data_solicitacao_informada": "Data da solicitação (controle)", "responsavel": "Responsável",
    "primeira_aparicao": "Primeira aparição", "ultima_aparicao": "Última aparição", "origens": "Origens",
    "inscricoes_de": "Inscrições de", "inscricoes_ate": "Inscrições até", "lideres": "Líderes",
    "desistencias": "Desistências", "data_evento": "Data do evento", "data_consentimento": "Data do consentimento",
    "primeira_interacao": "Primeira interação", "ultima_interacao": "Última interação",
    "ano_formacao": "Ano de formação", "data_nascimento": "Data de nascimento", "empresa_parceira": "Empresa parceira",
    "link_entrega": "Link da entrega", "mentor_cientifico": "Mentor científico", "desafio_atual": "Desafio atual",
}

LARGURA = {"nome": 32, "descricao": 60, "tematica": 50, "desafio": 45, "desafio_atual": 45, "detalhes": 45,
           "orientacao": 40, "observacoes": 40, "observacao": 35, "fonte": 42, "fontes": 42, "email": 30,
           "emails_alternativos": 30, "como_soube_texto": 30, "projeto_facens_texto": 30}

AVISO_LGPD = ("ATENÇÃO — LGPD: este arquivo contém dados pessoais (CPF, telefone, e-mail, data de nascimento). "
              "Uso restrito à equipe do FACE. Não envie por e-mail aberto nem publique.")


def rotulo(k):
    if k in ROTULOS:
        return ROTULOS[k]
    s = k.replace("_", " ")
    return s[:1].upper() + s[1:]


def _valor(v):
    if isinstance(v, (set, list, tuple)):
        return ", ".join(map(str, v))
    return v


def escrever_tabela(ws, linhas, linha_inicial=1, preencher=()):
    if not linhas:
        ws.cell(row=linha_inicial, column=1, value="(vazio)")
        return
    colunas = list(linhas[0].keys())
    for j, c in enumerate(colunas, 1):
        if c.startswith("_"):  # coluna técnica (chave para o importar_revisao.py), fica oculta
            ws.cell(row=linha_inicial, column=j, value=c)
            ws.column_dimensions[get_column_letter(j)].hidden = True
            continue
        cel = ws.cell(row=linha_inicial, column=j, value=rotulo(c) if c.islower() or "_" in c else c)
        cel.font = Font(bold=True, color="000000" if "preencher" in c else "FFFFFF")
        cel.fill = AMARELO if "preencher" in c else CAB
        cel.alignment = Alignment(vertical="center", wrap_text=True)
    for i, l in enumerate(linhas, linha_inicial + 1):
        for j, c in enumerate(colunas, 1):
            v = _valor(l.get(c))
            cel = ws.cell(row=i, column=j, value=v)
            if isinstance(v, (date, datetime)):
                cel.number_format = "DD/MM/YYYY"
            if c.startswith("_"):
                continue
            if "preencher" in c:
                cel.fill = AMARELO
            elif i % 2 == 0:
                cel.fill = LISTRA
            if isinstance(v, str) and len(v) > 40:
                cel.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                cel.alignment = Alignment(vertical="top")
    for j, c in enumerate(colunas, 1):
        if c.startswith("_"):
            continue
        largura = LARGURA.get(c)
        if largura is None:
            maior = max([len(str(_valor(l.get(c)) or "")) for l in linhas[:200]] + [len(rotulo(c))])
            largura = min(max(maior + 2, 9), 34)
        ws.column_dimensions[get_column_letter(j)].width = largura
    ws.row_dimensions[linha_inicial].height = 30
    ws.freeze_panes = ws.cell(row=linha_inicial + 1, column=2 if colunas[0] == "id" else 1)
    ws.auto_filter.ref = f"A{linha_inicial}:{get_column_letter(len(colunas))}{linha_inicial + len(linhas)}"


def _titulo(ws, linha, texto, tamanho=12):
    c = ws.cell(row=linha, column=1, value=texto)
    c.font = Font(bold=True, size=tamanho, color=AZUL)
    return linha + 1


def gravar_base(caminho, tabelas, estat, linhas_ano, contagens, avisos):
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    ws.sheet_view.showGridLines = False
    r = _titulo(ws, 1, "Base consolidada do FACE", 16)
    ws.cell(row=r, column=1, value=f"Gerada em {date.today():%d/%m/%Y} a partir das planilhas do Google Forms.").font = \
        Font(italic=True, color="595959")
    r += 1
    c = ws.cell(row=r, column=1, value=AVISO_LGPD)
    c.font = Font(bold=True, color="C00000")
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    ws.row_dimensions[r].height = 32
    r += 2
    r = _titulo(ws, r, "Totais")
    for k, v in estat.items():
        ws.cell(row=r, column=1, value=k).font = Font(bold=not k.startswith(" "))
        ws.cell(row=r, column=2, value=v)
        r += 1
    r += 1
    r = _titulo(ws, r, "Por ano")
    # indicadores nas linhas, anos nas colunas
    anos = [l["Ano"] for l in linhas_ano]
    c = ws.cell(row=r, column=1, value="Indicador")
    c.font, c.fill = Font(bold=True, color="FFFFFF"), CAB
    for j, ano in enumerate(anos, 2):
        c = ws.cell(row=r, column=j, value=ano)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), CAB
        c.alignment = Alignment(horizontal="right")
    r += 1
    for k in [k for k in linhas_ano[0] if k != "Ano"] if linhas_ano else []:
        ws.cell(row=r, column=1, value=k.replace("  · ", "    ")).font = Font(bold=not k.startswith(" "))
        for j, l in enumerate(linhas_ano, 2):
            v = l[k]
            cel = ws.cell(row=r, column=j, value="—" if v in (None, 0) and "%" not in k else v)
            cel.alignment = Alignment(horizontal="right")
            if "%" in k and v is not None:
                cel.value = v / 100
                cel.number_format = "0%"
        for j in range(1, len(anos) + 2):
            ws.cell(row=r, column=j).border = FINA
        r += 1
    r += 1
    nota = ("Observação: o controle de mentorias realizadas começou em 2024 (em 2023 o status vem da coluna "
            "'Marcada?'). 'Pedidos realizados' inclui os marcados em verde na planilha mesmo sem sessão registrada. "
            "Pedidos sem data contam no ano da planilha.")
    c = ws.cell(row=r, column=1, value=nota)
    c.font = Font(italic=True, color="595959")
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(anos) + 1)
    ws.row_dimensions[r].height = 45
    r += 2
    for titulo, cnt in contagens.items():
        r = _titulo(ws, r, titulo, 11)
        total = sum(cnt.values())
        for k, v in cnt.most_common(12):
            ws.cell(row=r, column=1, value=k)
            ws.cell(row=r, column=2, value=v)
            pc = ws.cell(row=r, column=3, value=v / total if total else 0)
            pc.number_format = "0%"
            pc.font = Font(color="7F7F7F")
            r += 1
        r += 1
    ws.column_dimensions["A"].width = 52
    for j in range(2, 10):
        ws.column_dimensions[get_column_letter(j)].width = 11
    if avisos:
        r = ws.max_row + 2
        r = _titulo(ws, r, "Avisos da leitura")
        for a in avisos:
            ws.cell(row=r, column=1, value=a)
            r += 1
    for nome, linhas in tabelas.items():
        escrever_tabela(wb.create_sheet(nome), linhas)
    wb.save(caminho)


def gravar_json(caminho, tabelas):
    def conv(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, set):
            return sorted(v)
        return v
    dados = {nome: [{k: conv(v) for k, v in l.items()} for l in linhas] for nome, linhas in tabelas.items()}
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


ORIENTACAO_REVISAO = {
    "Pessoas": "Confirme as uniões e separações. Na coluna Ação escreva OK, SEPARAR ou UNIR. Em branco = manter.",
    "Projetos": "Escreva OK, SEPARAR ou o nome correto do projeto. Em branco = manter.",
    "Dados inválidos": "Escreva o valor correto, OK (aceitar o que o script fez) ou APAGAR (deixar o dado vazio). "
                       "Célula vazia = decidir depois.",
    "Atividades": "Preencha a data e o local das viagens/eventos.",
    "Significado das cores": "A equipe pintou linhas nestas planilhas. O que cada cor quer dizer? "
                             "(ex.: verde = selecionado, vermelho = desistiu, rosa = faltou).",
}


def gravar_revisao(caminho, revisao, estat):
    wb = Workbook()
    ws = wb.active
    ws.title = "Leia-me"
    ws.sheet_view.showGridLines = False
    linhas = [
        ("Revisão da consolidação do FACE", "t1"),
        (f"Gerado em {date.today():%d/%m/%Y}", "nota"), ("", None),
        ("O que fazer", "t2"),
        ("Preencha só as colunas AMARELAS. Célula vazia = decidir depois (o item volta na próxima revisão).", None),
        ("Devolva esta planilha preenchida. O importar_revisao.py guarda as respostas em decisoes_revisao.json e "
         "elas passam a valer em todas as próximas consolidações (o que já foi decidido não volta para cá).", None),
        ("Não apague nem reordene colunas: há uma coluna oculta que identifica cada linha.", "nota"),
        ("", None), ("Pendências por aba", "t2"),
        *[(f"{len(v):>4}  {k} — {ORIENTACAO_REVISAO.get(k, '')}", None) for k, v in revisao.items() if v],
        ("", None),
        ("Sobre o CPF: cadastros antigos sem CPF são esperados (o CPF passou a ser pedido em meados de 2025) e não "
         "aparecem como pendência.", "nota"),
        ("", None), (AVISO_LGPD, "alerta"),
    ]
    for i, (t, estilo) in enumerate(linhas, 1):
        c = ws.cell(row=i, column=1, value=t)
        c.font = {"t1": Font(bold=True, size=16, color=AZUL), "t2": Font(bold=True, size=12, color=AZUL),
                  "nota": Font(italic=True, color="595959"), "alerta": Font(bold=True, color="C00000")}.get(
            estilo, Font())
    ws.column_dimensions["A"].width = 130
    for aba in ("Pessoas", "Projetos", "Dados inválidos", "Atividades", "Significado das cores"):
        itens = revisao.get(aba, [])
        w = wb.create_sheet(aba)
        w.cell(row=1, column=1, value=ORIENTACAO_REVISAO[aba]).font = Font(italic=True, color="595959")
        escrever_tabela(w, itens, linha_inicial=2)
        if aba == "Pessoas" and itens:
            dv = DataValidation(type="list", formula1='"OK,SEPARAR,UNIR"', allow_blank=True)
            w.add_data_validation(dv)
            col = get_column_letter(list(itens[0]).index("Ação (preencher)") + 1)
            dv.add(f"{col}3:{col}{len(itens) + 2}")
        for c in ("Problema", "Registro A", "Registro B", "Falta"):
            if itens and c in itens[0]:
                w.column_dimensions[get_column_letter(list(itens[0]).index(c) + 1)].width = 55
    wb.save(caminho)
