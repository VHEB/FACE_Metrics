"""
Leitores das planilhas do FACE.

Cada leitor recebe o caminho de um .xlsx e devolve uma lista de "registros":
dicionários com a pessoa (dados brutos já padronizados) e o fato que a linha
representa — um pedido de mentoria, uma sessão de mentoria realizada ou uma
inscrição em programa/viagem/evento.

Os leitores localizam as colunas pelo texto do cabeçalho (não pela posição),
então continuam funcionando se o Google Forms ganhar ou perder perguntas.
"""

import re
from pathlib import Path

from openpyxl import load_workbook

import normalizar as N


# ---------------------------------------------------------------------------
# Leitura genérica
# ---------------------------------------------------------------------------

MARCAS_CABECALHO = ("nome", "nome completo", "solicitante", "carimbo de data hora", "endereco de e mail", "smart money")


class Planilha:
    """Uma aba com cabeçalho localizado automaticamente."""

    def __init__(self, caminho, aba=None):
        self.caminho = Path(caminho)
        wb = load_workbook(caminho, data_only=True)
        if aba is None:
            ws = wb.worksheets[0]
        else:
            alvo = N.chave(aba)
            candidatas = [s for s in wb.worksheets if N.chave(s.title).startswith(alvo)]
            if not candidatas:
                raise ValueError(f"aba '{aba}' não encontrada em {self.caminho.name}")
            ws = candidatas[0]
        self.aba = ws.title.strip()
        self.linhas, self.cores = [], []
        for row in ws.iter_rows():
            self.linhas.append([c.value for c in row])
            self.cores.append([_rgb(c) for c in row])
        wb.close()
        self.ih = self._achar_cabecalho()
        cab = [N.texto(v) for v in self.linhas[self.ih]]
        # sub-cabeçalho (ex.: DATAS -> SOLICITAÇÃO | REALIZAÇÃO)
        inicio = self.ih + 1
        if inicio < len(self.linhas):
            sub = [N.chave(v) for v in self.linhas[inicio]]
            if any(s in {"solicitacao", "realizacao", "qtd dias"} for s in sub):
                for i, s in enumerate(sub):
                    if s:
                        while len(cab) <= i:
                            cab.append("")
                        cab[i] = N.texto(self.linhas[inicio][i])
                inicio += 1
        self.cab = cab
        self.chaves = [N.chave(c) for c in cab]
        self.inicio = inicio

    def _achar_cabecalho(self):
        melhor, melhor_n = 0, -1
        for i, linha in enumerate(self.linhas[:6]):
            ks = [N.chave(v) for v in linha]
            if any(k in MARCAS_CABECALHO or k.startswith("nome completo") for k in ks):
                n = sum(bool(k) for k in ks)
                if n > melhor_n:
                    melhor, melhor_n = i, n
        return melhor

    def cor(self, n_excel, i):
        """Cor de fundo (RRGGBB) da célula, ou ''."""
        linha = self.cores[n_excel - 1] if n_excel - 1 < len(self.cores) else []
        return linha[i] if i is not None and i < len(linha) else ""

    def legenda(self):
        """Lê a legenda de cores que a equipe coloca no fim da planilha (se houver)."""
        rotulos = {N.chave(x): x for x in N.LEGENDA_STATUS}
        mapa = {}
        for linha, cores in zip(self.linhas, self.cores):
            for i, v in enumerate(linha[:4]):
                k = N.chave(v)
                if k in rotulos and i < len(cores) and cores[i]:
                    mapa[cores[i]] = rotulos[k].lower()
        return mapa

    def col(self, *palavras, excluir=(), exato=False):
        """Índice da primeira coluna cujo cabeçalho contém todas as palavras."""
        for i, k in enumerate(self.chaves):
            if not k:
                continue
            if exato and k != palavras[0]:
                continue
            if all(p in k for p in palavras) and not any(e in k for e in excluir):
                return i
        return None

    def cols(self, *palavras, excluir=()):
        return [i for i, k in enumerate(self.chaves) if k and all(p in k for p in palavras)
                and not any(e in k for e in excluir)]

    def dados(self):
        """(número da linha no Excel, valores) das linhas com conteúdo."""
        for n, linha in enumerate(self.linhas[self.inicio:], start=self.inicio + 1):
            if any(N.texto(v) for v in linha):
                yield n, linha

    @staticmethod
    def v(linha, i):
        return linha[i] if i is not None and i < len(linha) else None


def _rgb(celula):
    f = celula.fill
    if f is None or f.fill_type is None or f.fgColor is None or f.fgColor.type != "rgb":
        return ""
    rgb = (f.fgColor.rgb or "")[-6:].upper()
    return "" if rgb in N.CORES_IGNORADAS else rgb


def fonte(pl, n):
    return {"arquivo": pl.caminho.name, "aba": pl.aba, "linha": n}


# ---------------------------------------------------------------------------
# Pessoa
# ---------------------------------------------------------------------------

def montar_pessoa(*, nome, email=None, telefone=None, cpf=None, rg=None, ra=None, nascimento=None, cep=None,
                  estado=None, vinculo=None, vinculo_padrao="", curso=None, curso_alumni=None, curso_docente=None,
                  ano_formacao=None, consentimento=False, cnpj=None):
    problemas = []
    bruto = N.texto(nome)
    if ";" in bruto and all(len(x.split()) >= 2 for x in bruto.split(";") if x.strip()):
        bruto = bruto.split(";")[0]  # duas pessoas no mesmo formulário: fica a primeira (dona do 1º e-mail)
    p = {"nome": N.nome_pessoa(bruto)}
    p["emails"], prob = N.emails(email)
    if prob:
        problemas.append(("e-mail", prob))
    p["telefone"], prob = N.telefone(telefone)
    if prob:
        problemas.append(("telefone", prob))
    p["cpf"], prob = N.cpf(cpf)
    if prob:
        problemas.append(("CPF", prob))
    p["rg"] = N.rg(rg)
    p["ra"], prob = N.ra(ra)
    if prob:
        problemas.append(("RA", prob))
    p["data_nascimento"] = N.data(nascimento)
    if p["data_nascimento"] and not (1930 <= p["data_nascimento"].year <= 2012):
        problemas.append(("data de nascimento", f"data improvável: {p['data_nascimento']:%d/%m/%Y}"))
        p["data_nascimento"] = None
    p["cep"] = N.cep(cep)
    p["estado"] = (re.search(r"\(([A-Z]{2})\)", N.texto(estado)) or [None, ""])[1] if estado else ""
    p["vinculo"] = N.vinculo(vinculo) or vinculo_padrao
    p["curso"], p["nivel"], p["semestre"], p["trilha"] = "", "", None, ""
    for origem in (curso, curso_alumni, curso_docente):
        c = N.curso(origem)
        if c[0]:
            p["curso"], p["nivel"], p["semestre"], p["trilha"] = c
            break
        if c[2] and not p["semestre"]:
            p["semestre"] = c[2]
    if not p["vinculo"] and p["curso"]:
        p["vinculo"] = "aluno"
    p["ano_formacao"] = N.ano(ano_formacao) if p["vinculo"] == "ex_aluno" else None
    p["consentimento_lgpd"] = bool(consentimento)
    p["cnpj"] = re.sub(r"\D", "", N.texto(cnpj)) if cnpj and len(re.sub(r"\D", "", N.texto(cnpj))) == 14 else ""
    return p, problemas


def pessoa_da_linha(pl, linha, vinculo_padrao="", **extras):
    """Monta a pessoa usando os nomes de coluna padrão dos formulários do FACE."""
    v = lambda i: pl.v(linha, i)
    i_email = pl.col("e mail") if pl.col("e mail") is not None else pl.col("email")
    i_tel = pl.col("celular") if pl.col("celular") is not None else (
        pl.col("whats") if pl.col("whats") is not None else pl.col("telefone"))
    i_curso_aluno = pl.col("curso", excluir=("qual curso", "voce fez", "da aula", "tipo curso", "nao tenha",
                                             "escolheu"))
    return montar_pessoa(
        nome=v(pl.col("nome completo") if pl.col("nome completo") is not None else pl.col("nome", exato=True)),
        email=v(i_email),
        telefone=v(i_tel),
        cpf=v(pl.col("cpf")),
        rg=v(pl.col("rg", exato=True)),
        ra=v(pl.col("ra", exato=True)),
        nascimento=v(pl.col("data de nascimento")),
        cep=v(pl.col("cep", exato=True)),
        estado=v(pl.col("estado")),
        vinculo=v(pl.col("vinculo")),
        vinculo_padrao=vinculo_padrao,
        curso=v(i_curso_aluno) or v(pl.col("escolheu outro")) or v(pl.col("nao tenha encontrado")),
        curso_alumni=v(pl.col("qual curso voce fez")),
        curso_docente=v(pl.col("da aula")),
        ano_formacao=v(pl.col("ano de formacao")),
        consentimento=N.chave(v(pl.col("concorda com o tratamento"))).startswith("sim"),
        cnpj=v(pl.col("cnpj")),
        **extras,
    )


def data_linha(pl, linha):
    i = pl.col("carimbo de data hora")
    if i is None:
        i = pl.col("smart money")  # 2024: a coluna do carimbo foi renomeada
    return N.data_hora(pl.v(linha, i))


# ---------------------------------------------------------------------------
# Pedidos de mentoria (formulários "Agendamento mentorias" e "Extensão")
# ---------------------------------------------------------------------------

def ler_pedidos(caminho, aba=None, origem="Programa de Mentorias", vinculo_padrao="", ano=None, **_):
    pl = Planilha(caminho, aba)
    v = pl.v
    registros = []
    i_marcada = pl.col("marcada")
    legenda = {**N.STATUS_POR_COR, **pl.legenda()}
    rotulos_legenda = {N.chave(x) for x in N.LEGENDA_STATUS}
    i_nome = pl.col("nome completo") if pl.col("nome completo") is not None else pl.col("nome", exato=True)
    for n, linha in pl.dados():
        pessoa, problemas = pessoa_da_linha(pl, linha, vinculo_padrao=vinculo_padrao)
        if not pessoa["nome"] and not pessoa["emails"]:
            continue
        if N.chave(pessoa["nome"]) in rotulos_legenda and not pessoa["emails"]:
            continue  # linha da legenda de cores
        cor = pl.cor(n, i_nome) or pl.cor(n, 0)
        quando = data_linha(pl, linha)
        if quando is None:
            problemas.append(("data", "linha sem carimbo de data/hora (preenchida à mão?)"))
        nome_proj_bruto = N.texto(v(linha, pl.col("tem um nome")))
        como = " | ".join(N.texto(v(linha, i)) for i in pl.cols("como voce") if N.texto(v(linha, i)))
        faz_parte = N.texto(v(linha, pl.col("faz parte de algum projeto")))
        registros.append({
            "tipo": "pedido", "fonte": fonte(pl, n), "data": quando, "pessoa": pessoa, "problemas": problemas,
            "origem": origem, "ano_referencia": ano,
            "turma_extensao": pessoa["trilha"] if origem.startswith("Extensão") else "",
            "projeto_nome_bruto": nome_proj_bruto,
            "projeto_nome": N.nome_projeto(nome_proj_bruto),
            "tematica": N.texto(v(linha, pl.col("descreva a tematica"))),
            "desafio": N.texto(v(linha, pl.col("qual o desafio atual"))),
            "projeto_facens_texto": faz_parte,
            "projeto_facens": N.projeto_facens(faz_parte),
            "trl": N.trl(v(linha, pl.col("trl"))),
            "formato": N.formato_mentoria(v(linha, pl.col("formato de mentoria"))),
            "formato_texto": N.texto(v(linha, pl.col("formato de mentoria"))),
            "periodo": N.periodo(v(linha, pl.col("melhor periodo"))),
            "horario_alternativo": N.texto(v(linha, pl.col("horario diferente"))),
            "como_soube_texto": como,
            "como_soube": N.como_soube(como),
            "observacao": N.texto(v(linha, pl.col("observacao", exato=True))),
            "anexo": N.texto(v(linha, pl.col("upload"))),
            "marcada_2023": N.texto(v(linha, i_marcada)) if i_marcada is not None else "",
            "status_planilha": legenda.get(cor, "sem marcação" if not cor else f"cor {N.nome_cor(cor)}"),
        })
    return registros


# ---------------------------------------------------------------------------
# Sessões de mentoria realizadas (abas "Realizadas")
# ---------------------------------------------------------------------------

def _achar_contatos(linha):
    """Nas abas de controle as colunas de e-mail e telefone às vezes estão trocadas."""
    email, tel = "", ""
    for v in linha:
        t = N.texto(v)
        if "@" in t and not email:
            email = t
        elif not tel and len(re.sub(r"\D", "", t)) >= 10 and not re.search(r"[a-zA-Z]{3,}", t) \
                and not hasattr(v, "year"):
            tel = t
    return email, tel


def ler_sessoes(caminho, aba, responsavel_padrao="", **_):
    pl = Planilha(caminho, aba)
    v = pl.v
    registros = []
    i_nome = pl.col("nome", exato=True)
    i_real = pl.col("realizacao")
    i_solic = pl.col("solicitacao")
    for n, linha in pl.dados():
        nome = N.texto(v(linha, i_nome))
        if not nome:
            continue
        email, tel = _achar_contatos(linha[: (pl.col("orientacao") or len(linha))])
        pessoa, problemas = montar_pessoa(nome=nome, email=email, telefone=tel, ra=v(linha, pl.col("ra", exato=True)),
                                          vinculo=v(linha, pl.col("vinculo")))
        data_real = N.data(v(linha, i_real))
        if data_real is None:
            problemas.append(("data", "sessão sem data de realização"))
        orientacao = N.texto(v(linha, pl.col("orientacao")))
        obs = N.texto(v(linha, pl.col("observacoes")))
        registros.append({
            "tipo": "sessao", "fonte": fonte(pl, n), "data": data_real, "pessoa": pessoa, "problemas": problemas,
            "data_solicitacao": N.data(v(linha, i_solic)) if i_solic is not None else None,
            "horario": N.hora(v(linha, pl.col("horario"))),
            "responsavel": N.texto(v(linha, pl.col("rae", exato=True))) or responsavel_padrao,
            "mentor": None, "area": "",
            "orientacao": orientacao, "observacoes": obs,
            "encaminhamentos": N.encaminhamentos(orientacao) + [e for e in N.encaminhamentos(obs)
                                                                if e.startswith("Wadhwani")],
            "projeto_nome": "",
        })
    return registros


def ler_sessoes_voluntarios(caminho, aba, **_):
    """Aba 'REALIZADAS - mentores voluntários' (2024): tem mentor, área e projeto."""
    pl = Planilha(caminho, aba)
    v = pl.v
    registros = []
    for n, linha in pl.dados():
        nome = N.texto(v(linha, pl.col("solicitante")))
        if not nome:
            continue
        pessoa, problemas = montar_pessoa(nome=nome, email=v(linha, pl.col("e mail", excluir=("mentor",))),
                                          telefone=v(linha, pl.col("whatsapp", excluir=("mentor",))),
                                          vinculo=v(linha, pl.col("vinculo")))
        mentor, _ = montar_pessoa(nome=v(linha, pl.col("mentor", exato=True)),
                                  email=v(linha, pl.col("e mail mentor")), telefone=v(linha, pl.col("whats mentor")))
        mentor["observacao"] = N.texto(v(linha, pl.col("observacoes")))
        registros.append({
            "tipo": "sessao", "fonte": fonte(pl, n), "data": N.data(v(linha, pl.col("data", exato=True))),
            "pessoa": pessoa, "problemas": problemas, "data_solicitacao": None, "horario": "",
            "responsavel": "", "mentor": mentor, "area": N.texto(v(linha, pl.col("area mentoria"))),
            "orientacao": "", "observacoes": "", "encaminhamentos": [],
            "projeto_nome": N.nome_projeto(v(linha, pl.col("projeto"))),
        })
    return registros


def ler_lista_espera(caminho, aba, atividade, **_):
    pl = Planilha(caminho, aba)
    v = pl.v
    registros = []
    for n, linha in pl.dados():
        nome = N.texto(v(linha, pl.col("nome", exato=True)))
        if not nome:
            continue
        pessoa, problemas = montar_pessoa(nome=nome, email=v(linha, pl.col("e mail")),
                                          telefone=v(linha, pl.col("whats")), vinculo=v(linha, pl.col("vinculo")))
        projeto = N.texto(v(linha, pl.col("projeto")))
        registros.append({
            "tipo": "inscricao", "fonte": fonte(pl, n), "data": None, "pessoa": pessoa, "problemas": problemas,
            "atividade": atividade, "papel": "participante", "status": "lista de espera",
            "detalhes": {"projeto": projeto}, "projeto": None, "grupo": None,
        })
    return registros


# ---------------------------------------------------------------------------
# Inscrições genéricas (viagens, transportes, eventos)
# ---------------------------------------------------------------------------

def ler_inscricoes(caminho, atividade, vinculo_padrao="", **_):
    pl = Planilha(caminho)
    v = pl.v
    registros = []
    i_ingresso = pl.col("ingresso")
    i_coment = pl.col("comentarios") if pl.col("comentarios") is not None else pl.col("duvidas")
    for n, linha in pl.dados():
        pessoa, problemas = pessoa_da_linha(pl, linha, vinculo_padrao=vinculo_padrao)
        if not pessoa["nome"]:
            continue
        detalhes = {}
        if i_ingresso is not None:
            detalhes["ingresso_adquirido"] = N.texto(v(linha, i_ingresso))
        if i_coment is not None and N.texto(v(linha, i_coment)):
            detalhes["comentario"] = N.texto(v(linha, i_coment))
        bruto_vinc = N.texto(v(linha, pl.col("vinculo")))
        if bruto_vinc and N.chave(bruto_vinc) not in {"aluno de graduacao", "colaborador", "alumni",
                                                      "comunidade externa"} and "sou" not in N.chave(bruto_vinc) \
                and "faco parte" not in N.chave(bruto_vinc):
            detalhes["vinculo_declarado"] = bruto_vinc
        cor = pl.cor(n, 1) or pl.cor(n, 0)
        if cor:
            detalhes["marcacao_cor"] = N.nome_cor(cor)
        registros.append({
            "tipo": "inscricao", "fonte": fonte(pl, n), "data": data_linha(pl, linha), "pessoa": pessoa,
            "problemas": problemas, "atividade": atividade, "papel": "participante", "status": "inscrito",
            "detalhes": detalhes, "projeto": None, "grupo": None,
        })
    return registros


# ---------------------------------------------------------------------------
# Programas com projeto: TCC Connect, Internacionalização, PIEMP
# ---------------------------------------------------------------------------

def ler_tcc_connect(caminho, atividade, **_):
    pl = Planilha(caminho)
    v = pl.v
    i_empresa = pl.col("com qual empresa")
    ignorar = ("duvidas", "entrega", "video pitch", "coluna")
    desafios = [i for i in range(i_empresa + 1, len(pl.cab)) if pl.chaves[i]
                and not any(x in pl.chaves[i] for x in ignorar)]
    i_status = [i for i in range(len(pl.cab)) if pl.chaves[i].startswith("coluna")]
    i_links = [i for i in range(len(pl.cab)) if "entrega" in pl.chaves[i] or "video pitch" in pl.chaves[i]]
    registros = []
    for n, linha in pl.dados():
        pessoa, problemas = pessoa_da_linha(pl, linha, vinculo_padrao="aluno")
        if not pessoa["nome"]:
            continue
        grupo = f"{pl.caminho.name}#{n}"
        escolhido = [(pl.cab[i].strip(), N.texto(v(linha, i))) for i in desafios if N.texto(v(linha, i))]
        status = next((N.texto(v(linha, i)) for i in i_status if N.texto(v(linha, i))), "")
        link = next((N.texto(v(linha, i)) for i in i_links if N.texto(v(linha, i))), "")
        empresa = N.texto(v(linha, i_empresa))
        comentarios = " | ".join(N.texto(v(linha, i)) for i in pl.cols("duvidas") if N.texto(v(linha, i)))
        titulo = escolhido[0][0] if escolhido else ""
        projeto = {
            "nome": N.nome_pessoa(titulo) if titulo.isupper() else titulo,
            "descricao": escolhido[0][1] if escolhido else "",
            "empresa_parceira": empresa, "origem": "TCC Connect", "link_entrega": link,
            "status": "desistiu" if N.chave(status).startswith("desist") else "",
            "observacao": comentarios,
        }
        if not titulo:
            projeto["nome"] = ""
            problemas.append(("projeto", "inscrição no TCC Connect sem desafio escolhido"))
        registros.append({
            "tipo": "inscricao", "fonte": fonte(pl, n), "data": data_linha(pl, linha), "pessoa": pessoa,
            "problemas": problemas, "atividade": atividade, "papel": "líder",
            "status": "desistiu" if projeto["status"] else "inscrito",
            "detalhes": {"empresa": empresa, "possui_grupo": N.texto(v(linha, pl.col("possui grupo"))),
                         "marcacao_cor": N.nome_cor(pl.cor(n, 1) or pl.cor(n, 0))},
            "projeto": projeto, "grupo": grupo,
        })
        texto_integrantes = N.texto(v(linha, pl.col("outros integrantes")))
        for k, m in enumerate(N.integrantes_texto(texto_integrantes)):
            p, prob = montar_pessoa(nome=m["nome"], email=m["email"], telefone=m["telefone"], ra=m["ra"],
                                    curso=m["curso"], vinculo_padrao="aluno")
            if m["problema"]:
                prob.append(("RA", m["problema"]))
            registros.append({
                "tipo": "inscricao", "fonte": {**fonte(pl, n), "campo": f"integrante {k + 2}"},
                "data": data_linha(pl, linha), "pessoa": p, "problemas": prob, "atividade": atividade,
                "papel": "integrante", "status": "desistiu" if projeto["status"] else "inscrito",
                "detalhes": {"empresa": empresa}, "projeto": None, "grupo": grupo,
            })
        if texto_integrantes and not N.integrantes_texto(texto_integrantes):
            registros[-1]["problemas"].append(("integrantes", f"não foi possível ler: '{texto_integrantes[:80]}'"))
    return registros


def ler_internacionalizacao(caminho, atividade, **_):
    pl = Planilha(caminho)
    v = pl.v
    registros = []
    for n, linha in pl.dados():
        pessoa, problemas = pessoa_da_linha(pl, linha)
        if not pessoa["nome"]:
            continue
        bruto = N.texto(v(linha, pl.col("ja tem um nome")))
        area = N.texto(v(linha, pl.col("qual area")))
        sem_projeto = bool(re.search(r"nao tenho (um )?projeto|ainda nao tenho", N.chave(area + " " + bruto)))
        como = N.texto(v(linha, pl.col("como voce ficou sabendo")))
        projeto = None
        if not sem_projeto:
            projeto = {
                "nome": N.nome_projeto(bruto), "descricao": N.texto(v(linha, pl.col("conte resumidamente"))),
                "area": area if len(area) < 60 and N.chave(area) not in {"na", ""} else "",
                "trl": N.trl(v(linha, pl.col("trl"))), "origem": "Internacionalização de Startups",
            }
        registros.append({
            "tipo": "inscricao", "fonte": fonte(pl, n), "data": data_linha(pl, linha), "pessoa": pessoa,
            "problemas": problemas, "atividade": atividade, "papel": "participante", "status": "inscrito",
            "detalhes": {"interesses": N.texto(v(linha, pl.col("principais interesses"))),
                         "como_soube": " | ".join(N.como_soube(como)), "como_soube_texto": como,
                         "marcacao_cor": N.nome_cor(pl.cor(n, 1) or pl.cor(n, 0))},
            "projeto": projeto, "grupo": f"{pl.caminho.name}#{n}",
        })
    return registros


def ler_piemp(caminho, atividade, **_):
    pl = Planilha(caminho)
    v = pl.v
    registros = []
    for n, linha in pl.dados():
        lider, problemas = montar_pessoa(
            nome=v(linha, pl.col("nome do estudante lider")), email=v(linha, pl.col("endereco de e mail")),
            telefone=v(linha, pl.col("whatsapp estudante lider")), ra=v(linha, pl.col("ra do estudante lider")),
            curso=v(linha, pl.col("curso", excluir=("integrante",))), vinculo_padrao="aluno")
        if not lider["nome"]:
            continue
        grupo = f"{pl.caminho.name}#{n}"
        partes = {
            "Proposta": pl.col("descreva brevemente"), "Problema": pl.col("qual problema"),
            "Público-alvo / modelo de negócio": pl.col("publico alvo"), "Solução": pl.col("proposta de solucao"),
            "Diferenciais": pl.col("principais diferenciais"),
        }
        descricao = "\n\n".join(f"{k}: {N.texto(v(linha, i))}" for k, i in partes.items() if N.texto(v(linha, i)))
        projeto = {
            "nome": N.nome_projeto(v(linha, pl.col("nome do projeto"))) or N.texto(v(linha, pl.col("nome do projeto"))),
            "descricao": descricao, "trl": N.trl(v(linha, pl.col("trl"))),
            "area": N.texto(v(linha, pl.col("melhor se enquadra"))),
            "ods": N.texto(v(linha, pl.col("principal ods"))), "origem": "PIEMP",
            "mentor_cientifico": N.texto(v(linha, pl.col("mentor cientifico"))),
            "link_entrega": N.texto(v(linha, pl.col("link do seu video"))),
            "observacao": N.texto(v(linha, pl.col("se sim compartilhe"))),
        }
        registros.append({
            "tipo": "inscricao", "fonte": fonte(pl, n), "data": data_linha(pl, linha), "pessoa": lider,
            "problemas": problemas, "atividade": atividade, "papel": "líder", "status": "inscrito",
            "detalhes": {"lattes": N.texto(v(linha, pl.col("lattes"))),
                         "aluno_sem_clt": N.texto(v(linha, pl.col("sem vinculo clt")))},
            "projeto": projeto, "grupo": grupo,
        })
        for i in pl.cols("do integrante"):
            for m in N.integrantes_texto(v(linha, i)):
                p, prob = montar_pessoa(nome=m["nome"], email=m["email"], telefone=m["telefone"], ra=m["ra"],
                                        curso=m["curso"], vinculo_padrao="aluno")
                if m["problema"]:
                    prob.append(("RA", m["problema"]))
                registros.append({
                    "tipo": "inscricao", "fonte": {**fonte(pl, n), "campo": pl.cab[i][:40]},
                    "data": data_linha(pl, linha), "pessoa": p, "problemas": prob, "atividade": atividade,
                    "papel": "integrante", "status": "inscrito", "detalhes": {}, "projeto": None, "grupo": grupo,
                })
    return registros


LEITORES = {
    "pedidos": ler_pedidos,
    "sessoes": ler_sessoes,
    "sessoes_voluntarios": ler_sessoes_voluntarios,
    "lista_espera": ler_lista_espera,
    "inscricoes": ler_inscricoes,
    "tcc_connect": ler_tcc_connect,
    "internacionalizacao": ler_internacionalizacao,
    "piemp": ler_piemp,
}
