"""
Consolidação de todas as planilhas do FACE numa base única e padronizada.

Uso:
    python -X utf8 consolidar.py PASTA_DAS_PLANILHAS --saida saida_consolidacao
    python -X utf8 consolidar.py PASTA_DAS_PLANILHAS --base-antiga face_dados.json

Gera, na pasta de saída:
    base_consolidada_face.xlsx   tabelas prontas para consulta (uma por aba) + Resumo com métricas
    base_consolidada_face.json   as mesmas tabelas, para carregar na nova plataforma
    revisao_consolidacao_face.xlsx  o que precisa de confirmação humana

--base-antiga (opcional): dump do sistema antigo, de onde é trazida a presença do SciBiz
(marcada à mão no sistema, não existe em planilha).

As planilhas originais nunca são alteradas.
"""

import argparse
import collections
import json
import os
import re
import statistics
from datetime import date, datetime
from pathlib import Path

import catalogo as C
import decisoes as D
import fontes as F
import normalizar as N
import saidas

HOJE = date.today()


# ---------------------------------------------------------------------------
# 1. Leitura
# ---------------------------------------------------------------------------

def localizar(pasta):
    arquivos = [p for p in Path(pasta).rglob("*.xlsx") if not p.name.startswith("~$")]
    nomes = {p: N.chave_compacta(re.sub(r"^[0-9a-f]{8}-", "", p.stem)) for p in arquivos}
    plano, avisos = [], []
    for rx, leitor, params in C.FONTES:
        achados = [p for p, k in nomes.items() if re.search(rx, k)]
        if not achados:
            avisos.append(f"Nenhuma planilha encontrada para o padrão '{rx}' ({leitor}).")
            continue
        if len(achados) > 1:
            achados.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            avisos.append(f"Mais de uma planilha para '{rx}': usando {achados[0].name}.")
        plano.append((achados[0], leitor, params, rx))
    usados = {p for p, _, _, _ in plano}
    for p in arquivos:
        if p not in usados:
            avisos.append(f"Planilha não reconhecida (ignorada): {p.name}. Cadastre-a em catalogo.py.")
    return plano, avisos


def ler_tudo(pasta):
    plano, avisos = localizar(pasta)
    registros = []
    for caminho, leitor, params, rx in plano:
        try:
            regs = F.LEITORES[leitor](caminho, **params)
        except ValueError as exc:
            avisos.append(str(exc))
            continue
        for r in regs:
            r["rid"] = len(registros)
            r["fonte"]["arquivo"] = re.sub(r"^[0-9a-f]{8}-", "", r["fonte"]["arquivo"])
            r["fonte"]["rx"] = rx
            registros.append(r)
    return registros, avisos


def data_ref(r):
    """Data do registro; sem data, usa o ano de referência da planilha."""
    if r.get("data"):
        return r["data"] if isinstance(r["data"], date) and not isinstance(r["data"], datetime) else r["data"].date()
    if r.get("data_solicitacao"):
        return r["data_solicitacao"]
    ano = r.get("ano_referencia") or (C.ATIVIDADES.get(r.get("atividade"), {}).get("edicao", "")[:4])
    try:
        return date(int(ano), 1, 1)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 2. Pessoas: unificação
# ---------------------------------------------------------------------------

class Unificador:
    """Union-find com travas: só une quando nada contradiz (CPF, RA, nome)."""

    def __init__(self, registros, dec=None):
        self.dec = dec or D.carregar(None)
        self.bloqueios = D.pares_separar(self.dec)
        self.regs = [r for r in registros if r["pessoa"]["nome"] or r["pessoa"]["emails"]]
        self.pai = {r["rid"]: r["rid"] for r in self.regs}
        self.info = {}
        for r in self.regs:
            p = r["pessoa"]
            tokens = set(N.chave_nome(p["nome"]).split()) or set(N.chave(p["nome"]).split())
            self.info[r["rid"]] = {"cpf": {p["cpf"]} - {""}, "ra": {p["ra"]} - {""}, "tokens": tokens,
                                   "primeiros": {N.chave(p["nome"]).split()[0]} if p["nome"] else set(),
                                   "ids": set(p["emails"]) | ({N.chave(p["nome"])} if p["nome"] else set())}
        self.nome = {r["rid"]: r["pessoa"]["nome"] for r in self.regs}
        self.mesclas_fracas = []   # (motivo, rid_a, rid_b)
        self.conflitos = []        # (motivo, rid_a, rid_b)

    def raiz(self, x):
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def tentar(self, a, b, motivo):
        ra_, rb = self.raiz(a), self.raiz(b)
        if ra_ == rb:
            return
        ia, ib = self.info[ra_], self.info[rb]
        for x, y in self.bloqueios:  # a equipe mandou manter separados
            if (ia["ids"] & x and ib["ids"] & y) or (ia["ids"] & y and ib["ids"] & x):
                return
        nomes_compativeis = bool(ia["tokens"] & ib["tokens"])
        if ia["cpf"] and ib["cpf"] and not (ia["cpf"] & ib["cpf"]):
            if motivo in ("e-mail", "RA"):
                self.conflitos.append((f"mesmo {motivo}, CPFs diferentes", a, b))
            return
        if motivo != "CPF" and ia["ra"] and ib["ra"] and not (ia["ra"] & ib["ra"]):
            mesmo_nome = N.chave_nome(self.nome[a]) == N.chave_nome(self.nome[b]) != ""
            if motivo == "e-mail" and mesmo_nome:
                # mesmo e-mail e mesmo nome completo: é a mesma pessoa com RA digitado errado
                self.conflitos.append(("mesmo e-mail e nome, RAs diferentes (unidos — conferir o RA)", a, b))
            else:
                if motivo == "e-mail" and nomes_compativeis:
                    self.conflitos.append(("mesmo e-mail, RAs diferentes", a, b))
                return
        if motivo in ("e-mail", "RA", "telefone") and not nomes_compativeis:
            if motivo == "e-mail":
                self.conflitos.append(("mesmo e-mail, nomes diferentes", a, b))
            return
        if motivo == "CPF" and not nomes_compativeis:
            self.conflitos.append(("mesmo CPF, nomes diferentes (unidos pelo CPF)", a, b))
        if motivo == "nome" or (motivo == "telefone" and N.chave_nome(self.nome[a]) != N.chave_nome(self.nome[b])):
            self.mesclas_fracas.append((motivo, a, b))
        self._unir(ra_, rb)

    def _unir(self, ra_, rb):
        ia, ib = self.info[ra_], self.info[rb]
        ia["ids"] |= ib["ids"]
        self.pai[rb] = ra_
        ia["cpf"] |= ib["cpf"]
        ia["ra"] |= ib["ra"]
        ia["tokens"] |= ib["tokens"]
        ia["primeiros"] |= ib["primeiros"]

    def executar(self):
        def chaves(r, tipo):
            p = r["pessoa"]
            if tipo == "CPF":
                return [p["cpf"]] if p["cpf"] else []
            if tipo == "e-mail":
                return p["emails"]
            if tipo == "RG":
                return [p["rg"]] if p["rg"] else []
            if tipo == "RA":
                return [p["ra"]] if p["ra"] else []
            if tipo == "telefone":
                prim = N.chave(p["nome"]).split()[:1]
                return [p["telefone"] + "|" + prim[0]] if p["telefone"] and prim else []
            if tipo == "nome":
                k = N.chave_nome(p["nome"])
                return [k] if len(k.split()) >= 3 else []
            return []

        for tipo in ("CPF", "e-mail", "RG", "RA", "telefone", "nome"):
            grupos = collections.defaultdict(list)
            for r in self.regs:
                for k in chaves(r, tipo):
                    grupos[k].append(r["rid"])
            for rids in grupos.values():
                for outro in rids[1:]:
                    self.tentar(rids[0], outro, tipo)
        # uniões pedidas pela equipe (passam por cima das travas)
        for grupo in D.grupos_unir(self.dec):
            rids = [r["rid"] for r in self.regs if self.info[r["rid"]]["ids"] & grupo
                    or set(r["pessoa"]["emails"]) & grupo or N.chave(r["pessoa"]["nome"]) in grupo]
            for outro in rids[1:]:
                a, b = self.raiz(rids[0]), self.raiz(outro)
                if a != b:
                    self._unir(a, b)
        clusters = collections.defaultdict(list)
        for r in self.regs:
            clusters[self.raiz(r["rid"])].append(r)
        return list(clusters.values())


def mais_recente(regs, campo, valido=bool):
    for r in sorted(regs, key=lambda r: data_ref(r) or date.min, reverse=True):
        v = r["pessoa"].get(campo)
        if valido(v):
            return v
    return None


def montar_pessoas(clusters):
    pessoas, pessoa_de = [], {}
    clusters.sort(key=lambda regs: min((data_ref(r) or date.max) for r in regs))
    for i, regs in enumerate(clusters, 1):
        pid = f"P{i:04d}"
        datas = [data_ref(r) for r in regs if data_ref(r)]
        nomes = collections.Counter(r["pessoa"]["nome"] for r in regs if r["pessoa"]["nome"])
        nome = max(nomes, key=lambda n: (len(N.chave_nome(n).split()), nomes[n], not n.isupper()))
        emails = []
        for r in sorted(regs, key=lambda r: data_ref(r) or date.min, reverse=True):
            for e in r["pessoa"]["emails"]:
                if e not in emails:
                    emails.append(e)
        ras = collections.Counter(r["pessoa"]["ra"] for r in regs if r["pessoa"]["ra"])
        vinc = mais_recente(regs, "vinculo")
        curso_regs = [r for r in regs if r["pessoa"]["curso"]]
        curso = mais_recente(curso_regs, "curso") if curso_regs else None
        nivel = next((r["pessoa"]["nivel"] for r in curso_regs if r["pessoa"]["curso"] == curso), "")
        consent = [data_ref(r) for r in regs if r["pessoa"]["consentimento_lgpd"]]
        tipos = collections.Counter(r["tipo"] for r in regs)
        vinculos_hist = sorted({r["pessoa"]["vinculo"] for r in regs if r["pessoa"]["vinculo"]})
        p = {
            "id": pid, "nome": nome,
            "cpf": mais_recente(regs, "cpf") or "", "ra": ras.most_common(1)[0][0] if ras else "",
            "rg": mais_recente(regs, "rg") or "",
            "email": emails[0] if emails else "", "emails_alternativos": ", ".join(emails[1:]),
            "telefone": mais_recente(regs, "telefone") or "",
            "data_nascimento": mais_recente(regs, "data_nascimento"),
            "cep": mais_recente(regs, "cep") or "", "estado": mais_recente(regs, "estado") or "",
            "vinculo_atual": N.ROTULO_VINCULO.get(vinc or "", ""),
            "vinculos_declarados": ", ".join(N.ROTULO_VINCULO[v] for v in vinculos_hist),
            "curso": curso or "", "nivel": {"graduacao": "Graduação", "pos": "Pós-graduação"}.get(nivel, ""),
            "ano_formacao": mais_recente(regs, "ano_formacao"),
            "cnpj": mais_recente(regs, "cnpj") or "",
            "consentimento_lgpd": "Sim" if consent else "",
            "data_consentimento": min(consent) if consent else None,
            "primeira_interacao": min(datas) if datas else None,
            "ultima_interacao": max(datas) if datas else None,
            "pedidos_mentoria": tipos["pedido"], "sessoes_mentoria": tipos["sessao"],
            "inscricoes": tipos["inscricao"],
            "fontes": ", ".join(sorted({r["fonte"]["arquivo"].replace("_respostas.xlsx", "").replace(".xlsx", "")
                                        for r in regs})),
        }
        pessoas.append(p)
        for r in regs:
            pessoa_de[r["rid"]] = pid
    return pessoas, pessoa_de


# ---------------------------------------------------------------------------
# 3. Projetos
# ---------------------------------------------------------------------------

def montar_projetos(registros, pessoa_de, revisao, dec):
    def chave_proj(nome, r):
        c = D.projeto_chave(dec, N.chave_compacta(nome))
        if c in dec["projetos"]["separar"]:  # equipe disse que são projetos diferentes
            c += "|" + str(pessoa_de.get(r["rid"]))
        return c

    candidatos = []  # (chave, dados, rid, papel)
    for r in registros:
        pid = pessoa_de.get(r["rid"])
        if r["tipo"] == "pedido" and r["projeto_nome"]:
            candidatos.append((chave_proj(r["projeto_nome"], r), {
                "nome": r["projeto_nome"], "descricao": r["tematica"], "desafio_atual": r["desafio"],
                "trl": r["trl"], "origem": f"Mentoria ({r['origem']})"}, r, "responsável"))
        elif r["tipo"] == "sessao" and r.get("projeto_nome"):
            candidatos.append((chave_proj(r["projeto_nome"], r), {"nome": r["projeto_nome"],
                                                                     "origem": "Mentoria (voluntários)"}, r,
                               "responsável"))
        elif r["tipo"] == "inscricao" and r.get("projeto") and r["projeto"].get("nome"):
            pj = r["projeto"]
            if pj["origem"] == "TCC Connect":
                k = f"tcc|{r['atividade']}|{N.chave_compacta(pj['nome'])}|{r['grupo']}"
            else:
                k = chave_proj(pj["nome"], r)
            candidatos.append((k, pj, r, r["papel"]))
    # integrantes listados no mesmo formulário do líder entram no mesmo projeto
    por_grupo = collections.defaultdict(list)
    for r in registros:
        if r["tipo"] == "inscricao" and r.get("grupo") and r["papel"] == "integrante":
            por_grupo[r["grupo"]].append(r)

    grupos = collections.defaultdict(lambda: {"dados": [], "membros": collections.OrderedDict()})
    for k, dados, r, papel in candidatos:
        g = grupos[k]
        g["dados"].append((data_ref(r), dados, r))
        pid = pessoa_de.get(r["rid"])
        if pid:
            g["membros"].setdefault(pid, papel)
        for m in por_grupo.get(r.get("grupo"), []):
            mid = pessoa_de.get(m["rid"])
            if mid:
                g["membros"].setdefault(mid, "integrante")

    # TCC Connect: inscrições da mesma equipe (membros em comum, mesmo desafio) viram um projeto
    tcc = collections.defaultdict(list)
    for k in list(grupos):
        if k.startswith("tcc|"):
            _, ativ, desafio, _ = k.split("|", 3)
            tcc[(ativ, desafio)].append(k)
    for (ativ, desafio), ks in tcc.items():
        mesclados = True
        while mesclados and len(ks) > 1:
            mesclados = False
            for a in ks:
                for b in ks:
                    if a < b and set(grupos[a]["membros"]) & set(grupos[b]["membros"]):
                        grupos[a]["dados"] += grupos[b]["dados"]
                        for pid, papel in grupos[b]["membros"].items():
                            grupos[a]["membros"].setdefault(pid, papel)
                        del grupos[b]
                        ks.remove(b)
                        mesclados = True
                        break
                if mesclados:
                    break

    # mesmo nome, pessoas sem nada em comum -> mescla, mas pede confirmação
    projetos, projeto_de = [], {}
    ordenados = sorted(grupos.items(), key=lambda kv: min(d for d, _, _ in kv[1]["dados"] if d) if any(
        d for d, _, _ in kv[1]["dados"]) else date.max)
    for i, (k, g) in enumerate(ordenados, 1):
        jid = f"J{i:04d}"
        dados = sorted(g["dados"], key=lambda x: x[0] or date.min)
        nomes = collections.Counter(d["nome"] for _, d, _ in dados)
        nome = max(nomes, key=lambda n: (nomes[n], not n.isupper(), n != n.lower(), -len(n)))
        base = k.split("|")[0]
        nome = dec["projetos"]["renomear"].get(base, nome)
        descricoes = list(dict.fromkeys(d.get("descricao", "") for _, d, _ in dados if d.get("descricao")))
        trls = [(dt, d["trl"]) for dt, d, _ in dados if d.get("trl") is not None]
        campo = lambda c: next((d.get(c) for _, d, _ in reversed(dados) if d.get(c)), "")
        datas = [dt for dt, _, _ in dados if dt]
        donos_por_registro = [pessoa_de.get(r["rid"]) for _, _, r in dados]
        p = {
            "id": jid, "nome": nome, "descricao": "\n---\n".join(descricoes[-3:]),
            "desafio_atual": campo("desafio_atual"), "area": campo("area"), "ods": campo("ods"),
            "empresa_parceira": campo("empresa_parceira"),
            "trl_inicial": trls[0][1] if trls else None, "trl_atual": trls[-1][1] if trls else None,
            "origens": ", ".join(sorted({d["origem"] for _, d, _ in dados})),
            "status": campo("status"), "link_entrega": campo("link_entrega"),
            "mentor_cientifico": campo("mentor_cientifico"), "observacao": campo("observacao"),
            "primeira_aparicao": min(datas) if datas else None, "ultima_aparicao": max(datas) if datas else None,
            "integrantes": len(g["membros"]),
        }
        projetos.append(p)
        for _, _, r in dados:
            projeto_de[r["rid"]] = jid
        g["id"] = jid
        if not k.startswith("tcc|") and "|" not in k and len({x for x in donos_por_registro if x}) > 1 \
                and base not in dec["projetos"]["confirmados"] and base not in dec["projetos"]["renomear"]:
            revisao["Projetos"].append({
                "id projeto": jid, "Projeto": nome, "Integrantes": len(g["membros"]),
                "Problema": f"{len({x for x in donos_por_registro if x})} pessoas diferentes citaram um projeto com "
                            "este nome. Foram reunidas num só projeto — confirmar se é a mesma equipe.",
                "Ação (preencher)": "", "_chave": json.dumps({"projetos": [base]}),
            })
    integrantes = []
    for k, g in grupos.items():
        for pid, papel in g["membros"].items():
            integrantes.append({"projeto_id": g["id"], "pessoa_id": pid, "papel": papel})

    # nomes quase iguais
    comp = {p["id"]: N.chave_compacta(p["nome"]) for p in projetos if p["origens"] != "TCC Connect"}
    itens = sorted(comp.items(), key=lambda x: x[1])
    for i, (a, ka) in enumerate(itens):
        for b, kb in itens[i + 1:]:
            if len(ka) >= 5 and len(kb) >= 5 and _distancia_1(ka, kb) and not D.projeto_par_decidido(dec, ka, kb):
                na = next(p["nome"] for p in projetos if p["id"] == a)
                nb = next(p["nome"] for p in projetos if p["id"] == b)
                revisao["Projetos"].append({
                    "id projeto": f"{a} e {b}", "Projeto": f"{na}  ×  {nb}", "Integrantes": "",
                    "Problema": "Nomes quase iguais — podem ser o mesmo projeto. NÃO foram reunidos.",
                    "Ação (preencher)": "", "_chave": json.dumps({"projetos": [ka, kb]}),
                })
    return projetos, integrantes, projeto_de


def _parecidos(a, b):
    """Até 2 letras de diferença (Nogueira × Moreira não; Francischetti × Francishcetti sim)."""
    if abs(len(a) - len(b)) > 2:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _distancia_1(a, b):
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))


# ---------------------------------------------------------------------------
# 4. Mentorias: pedidos, sessões e o vínculo entre eles
# ---------------------------------------------------------------------------

def montar_mentorias(registros, pessoa_de, projeto_de):
    pedidos_regs = [r for r in registros if r["tipo"] == "pedido" and r["rid"] in pessoa_de]
    sessoes_regs = [r for r in registros if r["tipo"] == "sessao" and r["rid"] in pessoa_de]

    # pedidos repetidos (mesma pessoa, mesma origem, até 10 dias) viram um só
    pedidos_regs.sort(key=lambda r: (pessoa_de[r["rid"]], r["origem"], data_ref(r) or date.min))
    unicos, duplicados = [], 0
    for r in pedidos_regs:
        ant = unicos[-1] if unicos else None
        if ant and pessoa_de[ant[0]["rid"]] == pessoa_de[r["rid"]] and ant[0]["origem"] == r["origem"] \
                and data_ref(r) and data_ref(ant[-1]) and (data_ref(r) - data_ref(ant[-1])).days <= 10:
            ant.append(r)
            duplicados += 1
        else:
            unicos.append([r])

    pedidos = []
    for grupo in unicos:
        primeiro, ultimo = grupo[0], grupo[-1]
        pedidos.append({
            "_rids": [x["rid"] for x in grupo],
            "pessoa_id": pessoa_de[primeiro["rid"]],
            "projeto_id": next((projeto_de.get(x["rid"]) for x in reversed(grupo) if projeto_de.get(x["rid"])), ""),
            "data_pedido": data_ref(primeiro) if primeiro.get("data") else None,
            "ano": (data_ref(primeiro) or date(primeiro["ano_referencia"], 1, 1)).year,
            "origem": primeiro["origem"], "turma_extensao": ultimo["turma_extensao"],
            "vinculo_no_pedido": N.ROTULO_VINCULO.get(ultimo["pessoa"]["vinculo"], ""),
            "curso_no_pedido": ultimo["pessoa"]["curso"],
            "nome_projeto_informado": ultimo["projeto_nome_bruto"],
            "tematica": ultimo["tematica"], "desafio": ultimo["desafio"],
            "projeto_facens": ", ".join(ultimo["projeto_facens"]), "projeto_facens_texto": ultimo["projeto_facens_texto"],
            "trl": ultimo["trl"], "formato": ultimo["formato"], "formato_texto": ultimo["formato_texto"],
            "periodo": ultimo["periodo"], "horario_alternativo": ultimo["horario_alternativo"],
            "como_soube": ", ".join(ultimo["como_soube"]), "como_soube_texto": ultimo["como_soube_texto"],
            "observacao": " | ".join(dict.fromkeys(x["observacao"] for x in grupo if x["observacao"])),
            "anexo": ultimo["anexo"], "status_planilha": ultimo["status_planilha"],
            "marcada_2023": primeiro["marcada_2023"],
            "formularios_enviados": len(grupo),
            "fonte": _fonte_txt(primeiro),
        })

    # sessões: mesma pessoa + mesma data em duas planilhas = uma sessão
    vistas, sessoes = {}, []
    for r in sorted(sessoes_regs, key=lambda r: data_ref(r) or date.min):
        chave_s = (pessoa_de[r["rid"]], r["data"])
        if r["data"] and chave_s in vistas:
            s = vistas[chave_s]
            s["encaminhamentos"] = ", ".join(dict.fromkeys(
                [e for e in s["encaminhamentos"].split(", ") if e] + r["encaminhamentos"]))
            s["fonte"] += " + " + _fonte_txt(r)
            continue
        s = {
            "_rid": r["rid"], "pessoa_id": pessoa_de[r["rid"]], "pedido_id": "",
            "projeto_id": projeto_de.get(r["rid"], ""), "data": r["data"], "horario": r["horario"],
            "data_solicitacao_informada": r["data_solicitacao"],
            "responsavel": r["responsavel"], "mentor": r["mentor"]["nome"] if r["mentor"] else "",
            "_mentor": r["mentor"], "area": r["area"],
            "encaminhamentos": ", ".join(r["encaminhamentos"]), "orientacao": r["orientacao"],
            "observacoes": r["observacoes"], "vinculo": N.ROTULO_VINCULO.get(r["pessoa"]["vinculo"], ""),
            "fonte": _fonte_txt(r),
        }
        vistas[chave_s] = s
        sessoes.append(s)

    # ids
    pedidos.sort(key=lambda p: (p["data_pedido"] or date(p["ano"], 1, 1), p["pessoa_id"]))
    for i, p in enumerate(pedidos, 1):
        p["id"] = f"M{i:04d}"
    sessoes.sort(key=lambda s: (s["data"] or date.min, s["pessoa_id"]))
    for i, s in enumerate(sessoes, 1):
        s["id"] = f"S{i:04d}"

    # cada sessão é ligada ao pedido mais recente da pessoa feito até a data da sessão (até 1 ano antes)
    por_pessoa = collections.defaultdict(list)
    for p in pedidos:
        por_pessoa[p["pessoa_id"]].append(p)
    for s in sessoes:
        if not s["data"]:
            continue
        # (acompanhamentos podem acontecer muito depois do pedido original)
        cands = [p for p in por_pessoa.get(s["pessoa_id"], []) if p["data_pedido"] and p["data_pedido"] <= s["data"]]
        if s["data_solicitacao_informada"]:
            exatos = [p for p in cands if p["data_pedido"] == s["data_solicitacao_informada"]]
            cands = exatos or cands
        if cands:
            ped = max(cands, key=lambda p: p["data_pedido"])
            s["pedido_id"] = ped["id"]
            if not s["projeto_id"]:
                s["projeto_id"] = ped["projeto_id"]

    sessoes_por_pedido = collections.defaultdict(list)
    for s in sessoes:
        if s["pedido_id"]:
            sessoes_por_pedido[s["pedido_id"]].append(s)
    for p in pedidos:
        ss = sorted(sessoes_por_pedido.get(p["id"], []), key=lambda s: s["data"])
        p["sessoes_registradas"] = len(ss)
        p["data_primeira_sessao"] = ss[0]["data"] if ss else None
        p["dias_ate_primeira_sessao"] = (ss[0]["data"] - p["data_pedido"]).days if ss and p["data_pedido"] else None
        p["encaminhamentos"] = ", ".join(dict.fromkeys(e for s in ss for e in s["encaminhamentos"].split(", ") if e))
        p["status"] = _status_pedido(p, ss)

    # mentores voluntários
    mentores, mentor_id = [], {}
    for s in sessoes:
        m = s.pop("_mentor")
        if not m or not m["nome"]:
            continue
        k = (m["emails"][0] if m["emails"] else N.chave(m["nome"]))
        if k not in mentor_id:
            mentor_id[k] = f"T{len(mentores) + 1:03d}"
            mentores.append({"id": mentor_id[k], "nome": m["nome"], "email": m["emails"][0] if m["emails"] else "",
                             "telefone": m["telefone"], "observacao": m.get("observacao", ""), "areas": set(),
                             "sessoes": 0})
        mt = next(x for x in mentores if x["id"] == mentor_id[k])
        mt["sessoes"] += 1
        if s["area"]:
            mt["areas"].add(s["area"])
        s["mentor"] = f"{mt['nome']} ({mt['id']})"
    for mt in mentores:
        mt["areas"] = ", ".join(sorted(mt["areas"]))
    for s in sessoes:
        s.pop("_rid", None)
    return pedidos, sessoes, mentores, duplicados


def _status_pedido(p, sessoes):
    cor = p["status_planilha"]
    if sessoes:
        return "realizado"
    m = N.chave(p["marcada_2023"])
    if m.startswith("sim"):
        return "realizado (sem data registrada)"
    if "sem retorno" in m:
        return "não respondeu"
    if "reagendar" in m:
        return "para reagendar"
    if cor == "realizado":
        return "realizado (sem sessão registrada)"
    if cor in ("não realizado", "agendado", "para agendar", "para reagendar", "não respondeu"):
        return cor
    if p["data_pedido"] and (HOJE - p["data_pedido"]).days <= 30:
        return "aguardando"
    return "sem registro"


def _fonte_txt(r):
    f = r["fonte"]
    base = f["arquivo"].replace("_respostas.xlsx", "").replace(".xlsx", "")
    return f"{base} › {f['aba']} › linha {f['linha']}" + (f" ({f['campo']})" if f.get("campo") else "")


# ---------------------------------------------------------------------------
# 5. Inscrições e atividades
# ---------------------------------------------------------------------------

def montar_inscricoes(registros, pessoa_de, projeto_de, base_antiga, pessoas):
    regs = [r for r in registros if r["tipo"] == "inscricao" and r["rid"] in pessoa_de]
    por_chave = collections.OrderedDict()
    ordem_papel = {"líder": 0, "participante": 1, "integrante": 2}
    duplicadas = 0
    for r in sorted(regs, key=lambda r: (ordem_papel.get(r["papel"], 3), data_ref(r) or date.min)):
        k = (pessoa_de[r["rid"]], r["atividade"])
        if k in por_chave:
            duplicadas += 1
            por_chave[k]["formularios_enviados"] += 1
            continue
        detalhes = {k2: v for k2, v in r["detalhes"].items() if v}
        por_chave[k] = {
            "pessoa_id": pessoa_de[r["rid"]], "atividade_id": r["atividade"],
            "data_inscricao": r["data"].date() if isinstance(r["data"], datetime) else r["data"],
            "papel": r["papel"],
            "status": _status_por_cor(r["atividade"], detalhes.get("marcacao_cor", ""), r["status"], r["papel"]),
            "vinculo_na_inscricao": N.ROTULO_VINCULO.get(r["pessoa"]["vinculo"], ""),
            "curso_na_inscricao": r["pessoa"]["curso"],
            "projeto_id": projeto_de.get(r["rid"], ""),
            "detalhes": "; ".join(f"{k2.replace('_', ' ')}: {v}" for k2, v in detalhes.items()),
            "marcacao_cor": detalhes.get("marcacao_cor", ""),
            "formularios_enviados": 1, "fonte": _fonte_txt(r),
        }
    inscricoes = list(por_chave.values())
    # integrantes herdam o projeto do líder
    projeto_do_grupo = {}
    for r in regs:
        if r.get("grupo") and projeto_de.get(r["rid"]):
            projeto_do_grupo[r["grupo"]] = projeto_de[r["rid"]]
    for r in regs:
        k = (pessoa_de[r["rid"]], r["atividade"])
        if not por_chave[k]["projeto_id"] and r.get("grupo") in projeto_do_grupo:
            por_chave[k]["projeto_id"] = projeto_do_grupo[r["grupo"]]
    # integrantes seguem o status do líder (concluiu, desistiu...)
    status_do_grupo = {r["grupo"]: por_chave[(pessoa_de[r["rid"]], r["atividade"])]["status"]
                       for r in regs if r.get("grupo") and r["papel"] == "líder"}
    for r in regs:
        k = (pessoa_de[r["rid"]], r["atividade"])
        if r["papel"] == "integrante" and por_chave[k]["status"] == "inscrito" and r.get("grupo") in status_do_grupo:
            por_chave[k]["status"] = status_do_grupo[r["grupo"]]

    # presença do SciBiz marcada à mão no sistema antigo
    presencas_aplicadas = 0
    if base_antiga:
        antigos = {r["pk"]: r["fields"] for r in base_antiga if r["model"] == "core.pessoa"}
        presentes = {}
        for r in base_antiga:
            if r["model"] == "core.eventoparticipante":
                pa = antigos.get(r["fields"]["pessoa"])
                if pa and pa.get("email"):
                    presentes[pa["email"].strip().lower()] = r["fields"]["presente"]
        email_para_pid = {}
        for p in pessoas:
            for e in [p["email"]] + [x.strip() for x in p["emails_alternativos"].split(",") if x.strip()]:
                email_para_pid[e] = p["id"]
        for email, presente in presentes.items():
            pid = email_para_pid.get(email)
            k = (pid, "scibiz-9")
            if pid and k in por_chave:
                por_chave[k]["status"] = "presente" if presente else "ausente"
                presencas_aplicadas += 1
    return inscricoes, duplicadas, presencas_aplicadas


def _status_por_cor(atividade, cor, atual, papel):
    """Traduz a cor que a equipe pintou na planilha (catalogo.py → 'cores') em status."""
    a = C.ATIVIDADES.get(atividade, {})
    if cor and cor in a.get("cores", {}):
        return a["cores"][cor]
    if not cor and atual == "inscrito" and papel != "integrante" and a.get("sem_cor"):
        return a["sem_cor"]
    return atual


def montar_atividades(inscricoes):
    por = collections.defaultdict(list)
    for i in inscricoes:
        por[i["atividade_id"]].append(i)
    atividades = []
    for aid, a in C.ATIVIDADES.items():
        ins = por.get(aid, [])
        datas = [i["data_inscricao"] for i in ins if i["data_inscricao"]]
        status = collections.Counter(i["status"] for i in ins)
        atividades.append({
            "id": aid, "tipo": a["tipo"], "programa": a["programa"], "edicao": a["edicao"],
            "nome": a.get("nome") or f"{a['programa']} {a['edicao']}",
            "data_evento": N.data(a.get("data_evento")), "local": a.get("local", ""),
            "inscricoes_de": min(datas) if datas else None, "inscricoes_ate": max(datas) if datas else None,
            "inscritos": len(ins), "lideres": sum(i["papel"] == "líder" for i in ins),
            "presentes": status["presente"] + status["participou"],
            "ausentes": status["ausente"] + status["não participou"],
            "concluintes": status["concluiu"], "desistencias": status["desistiu"],
            "sem_registro_de_presenca": status["inscrito"],
            "taxa_de_presenca": (round((status["presente"] + status["participou"]) /
                                       (status["presente"] + status["participou"] + status["ausente"]
                                        + status["não participou"]), 2)
                                 if (status["presente"] + status["participou"] + status["ausente"]
                                     + status["não participou"]) else None),
            "observacao": a.get("nota", ""),
        })
    return atividades


# ---------------------------------------------------------------------------
# 6. Revisão
# ---------------------------------------------------------------------------

def montar_revisao(registros, unif, pessoa_de, pessoas, revisao, inscricoes, dec):
    """Monta a planilha de revisão, sem repetir o que a equipe já decidiu (decisoes_revisao.json).
    Cada linha leva uma coluna oculta '_chave' para o importar_revisao.py saber a que ela se refere."""
    reg = {r["rid"]: r for r in registros}
    pnome = {p["id"]: p for p in pessoas}

    def ids_reg(rid):
        p = reg[rid]["pessoa"]
        return p["emails"] or [N.chave(p["nome"])]

    def ids_pessoa(p):
        es = [p["email"]] + [x.strip() for x in p["emails_alternativos"].split(",") if x.strip()]
        return [e for e in es if e] or [N.chave(p["nome"])]

    def resumo(rid):
        r = reg[rid]
        p = r["pessoa"]
        return f"{p['nome']} | {', '.join(p['emails']) or 'sem e-mail'} | {_fonte_txt(r)}"

    vistos = set()
    for motivo, a, b in unif.mesclas_fracas:
        pid = pessoa_de[a]
        if (pid, motivo) in vistos or D.pessoa_confirmada(dec, ids_reg(a), ids_reg(b)):
            continue
        vistos.add((pid, motivo))
        revisao["Pessoas"].append({
            "id pessoa": pid, "Nome no cadastro": pnome[pid]["nome"], "Situação": f"UNIDOS por {motivo}",
            "Registro A": resumo(a), "Registro B": resumo(b),
            "Problema": "Mesma pessoa? Unimos porque o " + motivo + " coincide, mas os e-mails são diferentes.",
            "Ação (preencher)": "", "_chave": json.dumps({"lados": [ids_reg(a), ids_reg(b)]}),
        })
    for motivo, a, b in unif.conflitos:
        if D.pessoa_confirmada(dec, ids_reg(a), ids_reg(b)):
            continue
        revisao["Pessoas"].append({
            "id pessoa": f"{pessoa_de[a]} / {pessoa_de[b]}",
            "Nome no cadastro": f"{pnome[pessoa_de[a]]['nome']} / {pnome[pessoa_de[b]]['nome']}",
            "Situação": "SEPARADOS" if pessoa_de[a] != pessoa_de[b] else "UNIDOS",
            "Registro A": resumo(a), "Registro B": resumo(b),
            "Problema": f"{motivo[0].upper() + motivo[1:]}. Pode ser e-mail/CPF de familiar ou erro de digitação.",
            "Ação (preencher)": "", "_chave": json.dumps({"lados": [ids_reg(a), ids_reg(b)]}),
        })
    # possíveis duplicatas: nome abreviado ("Rafaela Oliveira" × "Rafaela Andriotta de Oliveira")
    # ou com um sobrenome digitado diferente ("Murilo Nogueira Duarte" × "Murilo Moreira Duarte")
    por_nome = collections.defaultdict(list)
    for p in pessoas:
        pu = N.primeiro_ultimo(p["nome"])
        if pu:
            por_nome[pu].append(p)
    for pu, ps in por_nome.items():
        if len(ps) < 2:
            continue
        ligados = set()
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                ta, tb = N.chave_nome(a["nome"]).split(), N.chave_nome(b["nome"]).split()
                parecidos = set(ta) <= set(tb) or set(tb) <= set(ta) or (
                    len(ta) == len(tb) and sum(x != y for x, y in zip(ta, tb)) == 1
                    and all(_distancia_1(x, y) or x == y or _parecidos(x, y) for x, y in zip(ta, tb)))
                if parecidos and not D.pessoa_confirmada(dec, ids_pessoa(a), ids_pessoa(b)):
                    ligados |= {a["id"], b["id"]}
        ps = [p for p in ps if p["id"] in ligados]
        if len(ps) > 1:
            revisao["Pessoas"].append({
                "id pessoa": " / ".join(p["id"] for p in ps), "Nome no cadastro": " / ".join(p["nome"] for p in ps),
                "Situação": "SEPARADOS",
                "Registro A": " / ".join(p["email"] or "sem e-mail" for p in ps),
                "Registro B": " / ".join(p["fontes"][:60] for p in ps),
                "Problema": "Nomes parecidos, cadastros separados. Se for a mesma pessoa, escreva UNIR; "
                            "se forem pessoas diferentes, SEPARAR.",
                "Ação (preencher)": "", "_chave": json.dumps({"lados": [ids_pessoa(p) for p in ps]}),
            })
    # dados inválidos (uma linha por pessoa + problema, apontando para todas as linhas de origem)
    agrupados = collections.OrderedDict()
    for r in registros:
        for campo, problema in r["problemas"]:
            k = (pessoa_de.get(r["rid"], r["pessoa"]["nome"]), campo, problema)
            alvo = {"fonte": r["fonte"].get("rx", ""), "aba": r["fonte"]["aba"], "linha": r["fonte"]["linha"],
                    "integrante": r["fonte"].get("campo", ""), "campo": campo}
            if k not in agrupados:
                agrupados[k] = {
                    "id pessoa": pessoa_de.get(r["rid"], ""), "Nome": r["pessoa"]["nome"], "Campo": campo,
                    "Problema": problema, "Onde": _fonte_txt(r), "Valor correto (preencher)": "", "_alvos": [alvo],
                }
            else:
                agrupados[k]["_alvos"].append(alvo)
                agrupados[k]["Onde"] += f" (+{len(agrupados[k]['_alvos']) - 1} linha(s))" \
                    if "(+" not in agrupados[k]["Onde"] else ""
    for item in agrupados.values():
        n = len(item["_alvos"])
        if n > 1:
            item["Onde"] = re.sub(r" \(\+\d+ linha\(s\)\)$", "", item["Onde"]) + f" (+{n - 1} linha(s))"
        item["_chave"] = json.dumps({"alvos": item.pop("_alvos")})
        revisao["Dados inválidos"].append(item)
    # cores que ainda não têm significado no catalogo.py
    cores = collections.Counter((i["atividade_id"], i["marcacao_cor"]) for i in inscricoes if i["marcacao_cor"])
    for (aid, cor), n in sorted(cores.items()):
        a = C.ATIVIDADES[aid]
        if cor in a.get("cores", {}):
            continue
        revisao["Significado das cores"].append({
            "Planilha / atividade": a.get("nome") or f"{a['programa']} {a['edicao']}", "Cor": cor, "Linhas": n,
            "O que a cor significa? (preencher)": "",
        })


# ---------------------------------------------------------------------------
# 7. Métricas
# ---------------------------------------------------------------------------

def metricas(pessoas, pedidos, sessoes, inscricoes, atividades, projetos):
    tipo_ativ = {a["id"]: a["tipo"] for a in atividades}
    anos = sorted({p["ano"] for p in pedidos} | {s["data"].year for s in sessoes if s["data"]} |
                  {i["data_inscricao"].year for i in inscricoes if i["data_inscricao"]})
    linhas = []
    for ano in anos:
        ped = [p for p in pedidos if p["ano"] == ano]
        realizados = [p for p in ped if p["status"].startswith("realizado")]
        dias = [p["dias_ate_primeira_sessao"] for p in ped if p["dias_ate_primeira_sessao"] is not None]
        ins = [i for i in inscricoes if i["data_inscricao"] and i["data_inscricao"].year == ano]
        ativos = {p["pessoa_id"] for p in ped} | {s["pessoa_id"] for s in sessoes if s["data"] and s["data"].year == ano} \
            | {i["pessoa_id"] for i in ins}
        novos = sum(1 for p in pessoas if p["primeira_interacao"] and p["primeira_interacao"].year == ano)
        linhas.append({
            "Ano": ano, "Pessoas atendidas": len(ativos), "Pessoas novas": novos,
            "Pedidos de mentoria": len(ped),
            "  · Programa de Mentorias": sum(p["origem"] == "Programa de Mentorias" for p in ped),
            "  · Extensão": sum(p["origem"] == "Extensão" for p in ped),
            "Pedidos realizados": len(realizados),
            "% realizados": round(100 * len(realizados) / len(ped)) if ped else None,
            "Sessões registradas": sum(1 for s in sessoes if s["data"] and s["data"].year == ano),
            "Dias até a 1ª sessão (mediana)": statistics.median(dias) if dias else None,
            "Inscrições em programas": sum(tipo_ativ[i["atividade_id"]] == "programa" for i in ins),
            "Inscrições em viagens": sum(tipo_ativ[i["atividade_id"]] == "viagem" for i in ins),
            "Inscrições em eventos": sum(tipo_ativ[i["atividade_id"]] == "evento" for i in ins),
        })
    contagens = {
        "Vínculo atual das pessoas": collections.Counter(p["vinculo_atual"] or "(não informado)" for p in pessoas),
        "Cursos (alunos e ex-alunos)": collections.Counter(p["curso"] for p in pessoas if p["curso"]),
        "Como soube do Programa de Mentorias": collections.Counter(
            t for p in pedidos for t in p["como_soube"].split(", ") if t),
        "Encaminhamentos após a mentoria": collections.Counter(
            re.sub(r" turma \d+", "", e) for s in sessoes for e in s["encaminhamentos"].split(", ") if e),
        "Status dos pedidos de mentoria": collections.Counter(p["status"] for p in pedidos),
        "TRL atual dos projetos": collections.Counter(
            f"TRL {p['trl_atual']}" for p in projetos if p["trl_atual"] is not None),
        "Em quantas atividades cada pessoa esteve": collections.Counter(
            _faixa(p["pedidos_mentoria"] + p["inscricoes"]) for p in pessoas),
    }
    return linhas, contagens


def _faixa(n):
    return "1 atividade" if n <= 1 else ("2 atividades" if n == 2 else "3 ou mais")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # terminal do Windows
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", help="pasta com as planilhas (.xlsx) baixadas do Google Forms")
    ap.add_argument("--saida", default="saida_consolidacao")
    ap.add_argument("--base-antiga", help="dump JSON do sistema antigo (para trazer a presença do SciBiz)")
    ap.add_argument("--decisoes", help="decisoes_revisao.json (padrão: o que estiver na pasta das planilhas)")
    args = ap.parse_args()

    registros, avisos = ler_tudo(args.pasta)
    base_antiga = json.load(open(args.base_antiga, encoding="utf-8")) if args.base_antiga else None
    caminho_dec = args.decisoes or (Path(args.pasta) / "decisoes_revisao.json")
    dec = D.carregar(caminho_dec)
    decisoes_aplicadas = D.aplicar_dados(registros, dec)

    unif = Unificador(registros, dec)
    clusters = unif.executar()
    pessoas, pessoa_de = montar_pessoas(clusters)
    revisao = collections.defaultdict(list)
    projetos, integrantes, projeto_de = montar_projetos(registros, pessoa_de, revisao, dec)
    pedidos, sessoes, mentores, ped_dup = montar_mentorias(registros, pessoa_de, projeto_de)
    inscricoes, ins_dup, presencas = montar_inscricoes(registros, pessoa_de, projeto_de, base_antiga, pessoas)
    atividades = montar_atividades(inscricoes)
    montar_revisao(registros, unif, pessoa_de, pessoas, revisao, inscricoes, dec)
    for a in atividades:
        falta = [x for x, ok in (("data do evento", a["data_evento"]), ("local", a["local"])) if not ok]
        if falta and a["tipo"] in ("viagem", "evento"):
            revisao["Atividades"].append({"Atividade": a["nome"], "Tipo": a["tipo"], "Falta": " e ".join(falta),
                                          "Valor (preencher)": ""})
        if C.ATIVIDADES[a["id"]].get("confirmar"):
            revisao["Atividades"].append({"Atividade": a["nome"], "Tipo": a["tipo"],
                                          "Falta": C.ATIVIDADES[a["id"]]["confirmar"], "Valor (preencher)": ""})
    for p in pedidos:
        p.pop("_rids", None)
    for p in pessoas:
        p["projetos"] = sum(1 for x in integrantes if x["pessoa_id"] == p["id"])

    linhas_ano, contagens = metricas(pessoas, pedidos, sessoes, inscricoes, atividades, projetos)
    estat = {
        "Linhas lidas das planilhas": len(registros),
        "Planilhas lidas": len({r["fonte"]["arquivo"] for r in registros}),
        "Pessoas (cadastro único)": len(pessoas),
        "  · com CPF": sum(bool(p["cpf"]) for p in pessoas),
        "  · com RA": sum(bool(p["ra"]) for p in pessoas),
        "Projetos": len(projetos),
        "Pedidos de mentoria": len(pedidos),
        "  · formulários repetidos reunidos": ped_dup,
        "Sessões de mentoria registradas": len(sessoes),
        "  · ligadas a um pedido": sum(bool(s["pedido_id"]) for s in sessoes),
        "Inscrições em programas, viagens e eventos": len(inscricoes),
        "  · formulários repetidos reunidos": ins_dup,
        "Presenças do SciBiz trazidas do sistema antigo": presencas,
        "Mentores voluntários": len(mentores),
        "Correções da equipe aplicadas (revisão)": decisoes_aplicadas,
    }
    tabelas = {
        "Pessoas": pessoas, "Atividades": atividades, "Inscrições": inscricoes, "Projetos": projetos,
        "Integrantes": integrantes, "Pedidos de mentoria": pedidos, "Sessões de mentoria": sessoes,
        "Mentores": mentores,
    }
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    saidas.gravar_base(pasta / "base_consolidada_face.xlsx", tabelas, estat, linhas_ano, contagens, avisos)
    saidas.gravar_json(pasta / "base_consolidada_face.json", tabelas)
    saidas.gravar_revisao(pasta / "revisao_consolidacao_face.xlsx", revisao, estat)

    print("== Base consolidada ==")
    for k, v in estat.items():
        print(f"  {k}: {v}")
    print("\n== Por ano ==")
    for l in linhas_ano:
        print("  " + " | ".join(f"{k.strip(' ·')}: {v}" for k, v in l.items()))
    print("\n== Revisão ==")
    for aba, itens in revisao.items():
        print(f"  {aba}: {len(itens)}")
    if avisos:
        print("\n== Avisos ==")
        for a in avisos:
            print("  " + a)
    print(f"\nArquivos em: {pasta.resolve()}")


if __name__ == "__main__":
    main()
