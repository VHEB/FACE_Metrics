"""
Decisões da equipe vindas da planilha de revisão.

Ficam em `decisoes_revisao.json`, ao lado das planilhas (contém e-mails: NÃO vai para o Git).
As decisões são guardadas com chaves estáveis — e-mails das pessoas, nome do projeto,
linha de origem na planilha — e não com os IDs (P0001, J0001), que podem mudar quando
entram planilhas novas. Assim, cada decisão vale para todas as próximas consolidações.

Estrutura:
{
  "pessoas":  {"unir": [[e-mails...]], "separar": [[e-mails A], [e-mails B]]..., "confirmadas": [[e-mails...]]},
  "projetos": {"confirmados": [nome], "diferentes": [[nome, nome]], "unir": [[nome, nome]],
               "separar": [nome], "renomear": {nome: "Nome Novo"}},
  "dados":    [{"fonte", "aba", "linha", "integrante", "campo", "acao": aceitar|apagar|valor, "valor"}]
}
(nomes de projeto na forma compacta: minúsculas, sem acento e sem espaços)
"""

import json
from pathlib import Path

import normalizar as N

VAZIO = {
    "pessoas": {"unir": [], "separar": [], "confirmadas": []},
    "projetos": {"confirmados": [], "diferentes": [], "unir": [], "separar": [], "renomear": {}},
    "dados": [],
}


def carregar(caminho):
    if not caminho or not Path(caminho).exists():
        return json.loads(json.dumps(VAZIO))
    dados = json.load(open(caminho, encoding="utf-8"))
    for secao, padrao in VAZIO.items():
        if isinstance(padrao, dict):
            dados.setdefault(secao, {})
            for k, v in padrao.items():
                dados[secao].setdefault(k, json.loads(json.dumps(v)))
        else:
            dados.setdefault(secao, [])
    return dados


def salvar(dec, caminho):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dec, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Chaves
# ---------------------------------------------------------------------------

def chave_dado(fonte, campo):
    """Chave estável de um problema de dado: planilha (padrão do catálogo), aba, linha, integrante, campo."""
    return (fonte.get("rx", ""), N.chave(fonte.get("aba", "")), int(fonte.get("linha") or 0),
            N.chave(fonte.get("campo", "")), N.chave(campo))


def _chave_de_item(item):
    return (item["fonte"], N.chave(item["aba"]), int(item["linha"]), N.chave(item.get("integrante", "")),
            N.chave(item["campo"]))


def indice_dados(dec):
    return {_chave_de_item(i): i for i in dec["dados"]}


# ---------------------------------------------------------------------------
# Aplicação nos registros (antes da unificação de pessoas)
# ---------------------------------------------------------------------------

def aplicar_dados(registros, dec):
    """Aplica correções de campo e tira dos registros os problemas que a equipe já decidiu."""
    idx = indice_dados(dec)
    aplicadas = 0
    for r in registros:
        restantes = []
        for campo, problema in r["problemas"]:
            item = idx.get(chave_dado(r["fonte"], campo))
            if not item:
                restantes.append((campo, problema))
                continue
            if _aplicar(r, item):
                aplicadas += 1
        r["problemas"] = restantes
    return aplicadas


def _aplicar(r, item):
    p, campo, acao, valor = r["pessoa"], N.chave(item["campo"]), item["acao"], item.get("valor", "")
    if acao == "aceitar":
        return False
    if campo == "telefone":
        p["telefone"] = "" if acao == "apagar" else N.telefone(valor)[0]
    elif campo == "e mail":
        p["emails"] = [] if acao == "apagar" else N.emails(valor)[0]
    elif campo == "ra":
        p["ra"] = "" if acao == "apagar" else N.ra(valor)[0]
    elif campo == "cpf":
        p["cpf"] = "" if acao == "apagar" else N.cpf(valor)[0]
    elif campo == "data de nascimento":
        p["data_nascimento"] = None if acao == "apagar" else N.data(valor)
    elif campo == "data" and acao == "valor":
        r["data"] = N.data(valor)
    elif campo == "nome" and acao == "valor":
        p["nome"] = N.nome_pessoa(valor)
    else:
        return False
    return True


# ---------------------------------------------------------------------------
# Pessoas
# ---------------------------------------------------------------------------

def _ids(lista):
    return {N.chave(x) if not "@" in x else x.strip().lower() for x in lista if x}


def grupos_unir(dec):
    return [_ids(g) for g in dec["pessoas"]["unir"]]


def pares_separar(dec):
    return [(_ids(a), _ids(b)) for a, b in dec["pessoas"]["separar"]]


def pessoa_confirmada(dec, ids_a, ids_b):
    """A equipe já viu este par (confirmou, mandou unir ou separar)?"""
    a, b = _ids(ids_a), _ids(ids_b)
    for g in dec["pessoas"]["confirmadas"] + dec["pessoas"]["unir"]:
        g = _ids(g)
        if a & g and b & g:
            return True
    for x, y in pares_separar(dec):
        if (a & x and b & y) or (a & y and b & x):
            return True
    return False


# ---------------------------------------------------------------------------
# Projetos
# ---------------------------------------------------------------------------

def projeto_chave(dec, compacto):
    """Nome compacto final de um projeto, considerando pedidos de unir."""
    for a, b in dec["projetos"]["unir"]:
        if compacto == b:
            return a
    return compacto


def projeto_par_decidido(dec, a, b):
    pares = dec["projetos"]["diferentes"] + dec["projetos"]["unir"]
    return any({a, b} == set(p) for p in pares)
