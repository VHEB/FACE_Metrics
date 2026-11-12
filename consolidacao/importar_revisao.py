"""
Lê a planilha de revisão preenchida pela equipe e grava as respostas em decisoes_revisao.json.

Uso:
    python -X utf8 importar_revisao.py revisao_consolidacao_face.xlsx --decisoes decisoes_revisao.json

Depois rode o consolidar.py com --decisoes decisoes_revisao.json: as respostas são aplicadas
e os itens já decididos não voltam para a próxima planilha de revisão.

Como as respostas são entendidas (maiúsculas/acentos não importam):
    Pessoas          OK = está certo · UNIR · SEPARAR
    Projetos         OK = está certo · SEPARAR · UNIR/MESCLAR (pares) · qualquer outro texto = nome correto
    Dados inválidos  OK/manter = aceitar o que o script fez · "Em branco"/excluir/apagar = deixar vazio
                     "alterar para X" ou só o valor = usar X · célula vazia = decidir depois
    Atividades e cores: são mostradas na tela para serem copiadas para o catalogo.py.
"""

import argparse
import json
import re

from openpyxl import load_workbook

import catalogo as C
import decisoes as D
import normalizar as N

EMAIL = re.compile(r"[\w.%+\-]+@[\w.\-]+\.[a-z]{2,}", re.I)


def linhas(ws):
    todas = list(ws.iter_rows(values_only=True))
    if len(todas) < 3:
        return []
    cab = [str(c or "") for c in todas[1]]
    saida = []
    for n, r in enumerate(todas[2:], start=3):
        d = {cab[i]: r[i] for i in range(min(len(cab), len(r)))}
        d["_linha"] = n
        saida.append(d)
    return saida


def resposta(d):
    for k, v in d.items():
        if "preencher" in k and v not in (None, ""):
            return str(v).strip()
    return ""


def interpretar(texto):
    k = N.chave(texto)
    if not k:
        return None, ""
    if k in {"ok", "sim", "correto", "certo", "aceitar"} or k.startswith(("manter", "ok ")):
        return "aceitar", ""
    if k.startswith(("em branco", "excluir", "apagar", "remover", "deixar em branco", "vazio", "deixar vazio")):
        return "apagar", ""
    m = re.match(r"^\s*(?:alterar|mudar|corrigir|trocar)\s+para\s*:?\s*(.+)$", texto, flags=re.I)
    return "valor", (m.group(1) if m else texto).strip()


def lados_pessoa(d):
    """Identificadores (e-mails ou nome) de cada lado de uma linha da aba Pessoas."""
    if d.get("_chave"):
        ch = json.loads(d["_chave"])
        return ch["lados"]
    a, b = str(d.get("Registro A") or ""), str(d.get("Registro B") or "")
    if EMAIL.search(b) or "|" in b:
        textos = [a, b]
    else:
        textos = [t for t in a.split(" / ")]
    lados = []
    for t in textos:
        es = [e.lower() for e in EMAIL.findall(t)]
        lados.append(es or [N.chave(t.split("|")[0])])
    return lados


def rx_do_arquivo(nome):
    k = N.chave_compacta(re.sub(r"^[0-9a-f]{8}-", "", nome))
    for rx, _, _ in C.FONTES:
        if re.search(rx, k):
            return rx
    return ""


def chave_onde(onde):
    """'Planilha › Aba › linha 12 (integrante 2)' -> partes da chave."""
    partes = [p.strip() for p in str(onde).split("›")]
    m = re.match(r"linha (\d+)(?:\s*\((.+)\))?", partes[-1])
    return {"fonte": rx_do_arquivo(partes[0]), "aba": partes[1] if len(partes) > 2 else "",
            "linha": int(m.group(1)) if m else 0, "integrante": (m.group(2) or "") if m else ""}


def importar(caminho, dec):
    wb = load_workbook(caminho, data_only=True)
    resumo = {"pessoas": 0, "projetos": 0, "dados": 0, "sem resposta": 0}
    lembretes = []

    if "Pessoas" in wb.sheetnames:
        for d in linhas(wb["Pessoas"]):
            acao = N.chave(resposta(d))
            if not acao:
                resumo["sem resposta"] += 1
                continue
            lados = lados_pessoa(d)
            todos = [x for lado in lados for x in lado]
            if acao.startswith("unir"):
                dec["pessoas"]["unir"].append(todos)
            elif acao.startswith("separ"):
                for i in range(len(lados)):
                    for j in range(i + 1, len(lados)):
                        dec["pessoas"]["separar"].append([lados[i], lados[j]])
            else:
                dec["pessoas"]["confirmadas"].append(todos)
            resumo["pessoas"] += 1

    if "Projetos" in wb.sheetnames:
        for d in linhas(wb["Projetos"]):
            texto = resposta(d)
            acao = N.chave(texto)
            if not acao:
                resumo["sem resposta"] += 1
                continue
            if d.get("_chave"):
                nomes = json.loads(d["_chave"])["projetos"]
            else:
                nomes = [N.chave_compacta(x) for x in str(d.get("Projeto") or "").split("×")]
            P = dec["projetos"]
            if len(nomes) == 2:
                if acao.startswith(("unir", "mesclar")):
                    P["unir"].append(nomes)
                elif acao in {"ok", "certo", "correto"} or acao.startswith(("separ", "nao", "diferente")):
                    P["diferentes"].append(nomes)
                else:
                    P["unir"].append(nomes)
                    P["renomear"][nomes[0]] = texto
            else:
                if acao in {"ok", "certo", "correto"}:
                    P["confirmados"].append(nomes[0])
                elif acao.startswith("separ"):
                    P["separar"].append(nomes[0])
                else:
                    P["renomear"][nomes[0]] = texto
            resumo["projetos"] += 1

    if "Dados inválidos" in wb.sheetnames:
        existentes = D.indice_dados(dec)
        for d in linhas(wb["Dados inválidos"]):
            acao, valor = interpretar(resposta(d))
            if acao is None:
                resumo["sem resposta"] += 1
                continue
            alvos = json.loads(d["_chave"])["alvos"] if d.get("_chave") else [chave_onde(d.get("Onde", ""))]
            for alvo in alvos:
                if not alvo["fonte"]:
                    lembretes.append(f"Dados inválidos, linha {d['_linha']}: planilha de origem não reconhecida.")
                    continue
                item = {**alvo, "campo": alvo.get("campo") or str(d.get("Campo") or ""), "acao": acao,
                        "valor": valor, "pessoa": str(d.get("Nome") or ""), "problema": str(d.get("Problema") or "")}
                k = D._chave_de_item(item)
                if k in existentes:
                    dec["dados"].remove(existentes[k])
                dec["dados"].append(item)
                existentes[k] = item
            resumo["dados"] += 1

    for aba in ("Atividades", "Significado das cores"):
        if aba in wb.sheetnames:
            for d in linhas(wb[aba]):
                r = resposta(d)
                if r:
                    ident = " · ".join(str(v) for k, v in d.items() if v and "preencher" not in k
                                       and not k.startswith("_") and k not in ("Linhas",))
                    lembretes.append(f"[{aba}] {ident}  →  {r}")

    # remove repetições
    for k in ("unir", "confirmadas"):
        vistos, unicos = set(), []
        for g in dec["pessoas"][k]:
            t = tuple(sorted(set(g)))
            if t not in vistos:
                vistos.add(t)
                unicos.append(sorted(set(g)))
        dec["pessoas"][k] = unicos
    for k in ("confirmados", "separar"):
        dec["projetos"][k] = sorted(set(dec["projetos"][k]))
    return resumo, lembretes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("revisao", help="planilha de revisão preenchida")
    ap.add_argument("--decisoes", default="decisoes_revisao.json")
    args = ap.parse_args()
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    dec = D.carregar(args.decisoes)
    resumo, lembretes = importar(args.revisao, dec)
    D.salvar(dec, args.decisoes)
    print("Respostas importadas:", ", ".join(f"{k}: {v}" for k, v in resumo.items()))
    if lembretes:
        print("\nPara o catalogo.py (datas, locais e significado das cores):")
        for l in lembretes:
            print("  " + l)
    print(f"\nDecisões salvas em {args.decisoes}")


if __name__ == "__main__":
    main()
