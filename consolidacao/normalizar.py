"""
Funções e dicionários de padronização usados pela consolidação.

Tudo que é "conhecimento do FACE" (nomes de cursos, programas, categorias) fica
nos dicionários deste arquivo, para ser editado sem mexer na lógica.
"""

import re
import unicodedata
from datetime import date, datetime, time

# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

INVISIVEIS = re.compile(r"[​‌‍⁠﻿­]")
ESPACOS_ESPECIAIS = re.compile(r"[   ]")
PARTICULAS = {"da", "das", "de", "do", "dos", "e", "di", "du", "del", "van", "von"}


def texto(v):
    """Converte qualquer célula em texto limpo ('' se vazio)."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    s = str(v)
    s = INVISIVEIS.sub("", s)
    s = ESPACOS_ESPECIAIS.sub(" ", s)
    linhas = [re.sub(r"[ \t]+", " ", l).strip() for l in s.replace("\r", "\n").split("\n")]
    s = "\n".join(l for l in linhas if l).strip()
    return "" if s.lower() in {"none", "nan", "-", ".", "..", "n/a", "na", "nda"} else s


def sem_acento(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def chave(s):
    """Chave de comparação: minúsculas, sem acento, só letras/números/espaço."""
    s = sem_acento(texto(s).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def chave_compacta(s):
    return chave(s).replace(" ", "")


# ---------------------------------------------------------------------------
# Pessoa
# ---------------------------------------------------------------------------

def nome_pessoa(v):
    s = texto(v)
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s.replace("\n", " ")).strip(" .,;-")
    tokens = s.split(" ")
    if s.isupper() or s.islower() or any(t[:1].islower() and t.lower() not in PARTICULAS for t in tokens):
        palavras = []
        for i, p in enumerate(s.lower().split(" ")):
            if i > 0 and p in PARTICULAS:
                palavras.append(p)
            else:
                palavras.append("-".join(x[:1].upper() + x[1:] for x in p.split("-")))
        s = " ".join(palavras)
    return s


def chave_nome(nome):
    """Nome normalizado para casar pessoas (exige ao menos 2 palavras)."""
    k = chave(nome)
    partes = [p for p in k.split() if p not in PARTICULAS]
    return " ".join(partes) if len(partes) >= 2 else ""


def primeiro_ultimo(nome):
    partes = [p for p in chave(nome).split() if p not in PARTICULAS]
    return (partes[0], partes[-1]) if len(partes) >= 2 else None


DOMINIOS_CORRIGIDOS = {
    "gnail.com": "gmail.com", "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gmail.com.br": "gmail.com",
    "gmail.co": "gmail.com", "gamil.com": "gmail.com", "gmail.con": "gmail.com", "gmeil.com": "gmail.com",
    "hotmal.com": "hotmail.com", "hotmai.com": "hotmail.com", "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com", "outlook.con": "outlook.com", "icloud.con": "icloud.com",
}
EMAIL_OK = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def emails(v):
    """Retorna (lista de e-mails válidos, problema ou '')."""
    s = sem_acento(texto(v).lower().replace("mailto:", ""))
    if not s:
        return [], ""
    partes = [p.strip(" .;,<>()") for p in re.split(r"[;,\s/]+", s) if p.strip()]
    validos, problema = [], ""
    for p in partes:
        if "@" not in p:
            continue
        usuario, _, dominio = p.rpartition("@")
        if dominio in DOMINIOS_CORRIGIDOS:
            problema = f"domínio corrigido: {dominio} → {DOMINIOS_CORRIGIDOS[dominio]}"
            dominio = DOMINIOS_CORRIGIDOS[dominio]
        e = f"{usuario}@{dominio}"
        if EMAIL_OK.match(e) and e not in validos:
            validos.append(e)
    if not validos:
        problema = f"e-mail inválido: '{texto(v)[:60]}'"
    elif len(partes) > 1 and len(validos) > 1:
        problema = problema or "campo com mais de um e-mail"
    return validos, problema


DDDS = {11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44, 45,
        46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82, 83,
        84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99}


def telefone(v):
    """Retorna (telefone E.164 ou '', problema ou '')."""
    s = texto(v)
    if not s:
        return "", ""
    d = re.sub(r"\D", "", s)
    if s.strip().startswith("+") and not d.startswith("55"):
        if not (len(d) in (10, 11) and int(d[:2]) in DDDS):  # "+15 9..." é DDD digitado com "+"
            return "+" + d, "telefone internacional (mantido)"
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) == 12 and d.startswith("0"):
        d = d[1:]
    if len(d) in (10, 11) and int(d[:2]) not in DDDS:
        return "", f"DDD inexistente ({d[:2]}) — telefone provavelmente digitado errado"
    if len(d) == 11 and d[2] == "9":
        return "+55" + d, ""
    if len(d) == 10 and d[2] in "6789":
        return "+55" + d[:2] + "9" + d[2:], "celular sem o 9º dígito (acrescentado)"
    if len(d) == 10 and d[2] in "2345":
        return "+55" + d, ""
    if len(d) == 9 and d[0] == "9":
        return "+5515" + d, "sem DDD (assumido 15)"
    if len(d) == 8 and d[0] in "6789":
        return "+55159" + d, "sem DDD e sem 9º dígito (assumido 15)"
    return "", f"telefone fora do padrão: {len(d)} dígitos"


def cpf(v):
    """Retorna (cpf 11 dígitos ou '', problema ou '')."""
    s = texto(v)
    if not s:
        return "", ""
    d = re.sub(r"\D", "", s)
    if 8 <= len(d) < 11:
        d = d.zfill(11)  # Excel come zeros à esquerda
    if len(d) != 11 or len(set(d)) == 1:
        return "", f"CPF inválido ({len(d)} dígitos)"
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(d[n]):
            return "", "CPF com dígito verificador inválido"
    return d, ""


def rg(v):
    s = re.sub(r"[^0-9xX]", "", texto(v)).upper()
    return s if 5 <= len(s) <= 14 else ""


def ra(v):
    """Retorna (RA ou '', problema ou ''). RA Facens = 6 dígitos."""
    s = texto(v)
    if not s:
        return "", ""
    m = re.fullmatch(r"(\d+)\.0+", s)
    if m:
        s = m.group(1)
    s = re.sub(r"^ra[:\s]*", "", s, flags=re.I).strip()
    if re.fullmatch(r"\d{6}", s):
        return s, ""
    achados = re.findall(r"(?<!\d)\d{6}(?!\d)", s)
    if len(achados) == 1:
        return achados[0], ""
    if re.fullmatch(r"\d+", s):
        return "", f"RA fora do padrão ({len(s)} dígitos): {s}"
    return "", f"texto no lugar do RA: '{s[:40]}'"


def cep(v):
    d = re.sub(r"\D", "", texto(v))
    if len(d) == 7:
        d = "0" + d
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else ""


def data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = texto(v)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            pass
    return None


def data_hora(v):
    if isinstance(v, datetime):
        return v.replace(microsecond=0)
    d = data(v)
    return datetime.combine(d, time()) if d else None


def ano(v):
    s = texto(v)
    m = re.search(r"(19[5-9]\d|20[0-4]\d)", s)
    return int(m.group(1)) if m else None


def hora(v):
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, datetime):
        return v.strftime("%H:%M")
    s = texto(v).lower().replace(" ", "")
    m = re.match(r"^(\d{1,2})(?:[:h](\d{2}))?h?$", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
    return ""


# ---------------------------------------------------------------------------
# Vínculo
# ---------------------------------------------------------------------------

VINCULOS = {"aluno", "ex_aluno", "comunidade_externa", "docente", "colaborador"}


def vinculo(v):
    k = chave(v)
    if not k:
        return ""
    if "ex aluno" in k or "alumni" in k:
        return "ex_aluno"
    if "comunidade" in k or "nao tenho vinculo" in k or "irma" in k:
        return "comunidade_externa"
    if "professor" in k or "docente" in k:
        return "docente"
    if "colaborador" in k or "funcionario" in k:
        return "colaborador"
    if "aluno" in k or "graduacao" in k or "tecnologo" in k or "pos" in k:
        return "aluno"
    return ""


ROTULO_VINCULO = {
    "aluno": "Aluno(a)", "ex_aluno": "Ex-aluno(a)", "comunidade_externa": "Comunidade externa",
    "docente": "Docente", "colaborador": "Colaborador(a)", "": "",
}

# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------

# (nome canônico, nível)
CURSOS = [
    ("Arquitetura e Urbanismo", "graduacao", ["arquitetura e urbanismo", "arquitetura", "arquitetura urbanismo"]),
    ("Biomedicina", "graduacao", ["biomedicina"]),
    ("Enfermagem", "graduacao", ["enfermagem"]),
    ("Engenharia Agronômica", "graduacao", ["engenharia agronomica", "agronomia"]),
    ("Engenharia Civil", "graduacao", ["engenharia civil", "eng civil", "civil"]),
    ("Engenharia de Computação", "graduacao", ["engenharia de computacao", "engenharia da computacao",
                                               "eng da computacao", "eng de computacao", "eng computacao",
                                               "engenheira de computacao", "engenharia computacao"]),
    ("Engenharia Elétrica", "graduacao", ["engenharia eletrica", "eng eletrica", "eletrica"]),
    ("Engenharia Mecânica", "graduacao", ["engenharia mecanica", "eng mecanica", "mecanica"]),
    ("Engenharia Mecatrônica", "graduacao", ["engenharia mecatronica", "eng mecatronica", "mecatronica"]),
    ("Engenharia de Produção", "graduacao", ["engenharia de producao", "eng producao", "eng de producao",
                                             "engenharia producao"]),
    ("Engenharia Química", "graduacao", ["engenharia quimica", "eng quimica", "quimica"]),
    ("Medicina", "graduacao", ["medicina"]),
    ("Medicina Veterinária", "graduacao", ["medicina veterinaria", "veterinaria"]),
    ("Odontologia", "graduacao", ["odontologia"]),
    ("Psicologia", "graduacao", ["psicologia"]),
    ("Tecnologia em Análise e Desenvolvimento de Sistemas", "graduacao",
     ["tecnologia em analise e desenvolvimento de sistemas", "tecnologo em analise e desenvolvimento de sistemas",
      "analise e desenvolvimento de sistemas", "ads"]),
    ("Tecnologia em Gestão de TI", "graduacao", ["tecnologia em gestao de t i", "gestao de ti", "gestao de t i",
                                                 "tecnologia em gestao de ti"]),
    ("Tecnologia em Jogos Digitais", "graduacao", ["tecnologia em jogos digitais", "jogos digitais"]),
    ("Especialização em Lean Six Sigma (Black Belt)", "pos",
     ["especializacao em lean six sigma com certificacao black belt", "pos graduacao lean six sigma",
      "lean six sigma"]),
    ("Pós-graduação em Arquitetura de Software", "pos", ["pos graduacao arquitetura de software"]),
    ("MBA em Gestão de Projetos", "pos", ["mba gestao de projetos"]),
    ("Pós-graduação (curso não informado)", "pos", ["pos graduacao", "pos"]),
]
_CURSO_POR_CHAVE = {a: (nome, nivel) for nome, nivel, apelidos in CURSOS for a in apelidos}
_APELIDOS_ORDENADOS = sorted(_CURSO_POR_CHAVE, key=len, reverse=True)

# Sufixos que são turma/trilha da Extensão, não parte do nome do curso
TRILHAS = {"projeto startup": "Projeto Startup", "gestao da inovacao": "Gestão da Inovação", "tcc 1": "TCC 1"}

NAO_E_CURSO = {"outro", "outros", "nao sou aluna", "nao sou aluno", "ingles", "2022s1"}


def curso(v):
    """Retorna (curso canônico, nível, semestre, trilha). Curso '' se não reconhecido."""
    bruto = texto(v)
    k = chave(bruto)
    if not k or k in NAO_E_CURSO:
        return "", "", None, ""
    semestre = None
    m = re.search(r"(\d{1,2})\s*(?:o|º|°)?\s*(?:semestre|sem)\b", sem_acento(bruto.lower()))
    if not m:
        m = re.search(r"\b(\d{1,2})\s*o?\b", k) if re.search(r"semestre|sem\b|^\d", k) else None
    if not m:
        m = re.search(r"(\d{1,2})\s*[º°]", bruto)
    if m:
        semestre = int(m.group(1))
    elif "primeiro" in k:
        semestre = 1
    elif "terceiro" in k:
        semestre = 3
    trilha = ""
    for t_chave, t_nome in TRILHAS.items():
        if k.endswith(t_chave) and k != t_chave:
            trilha = t_nome
            k = k[: -len(t_chave)].strip()
    k = re.sub(r"\b\d{1,2}\s*o?\b|\bsemestre\b|\bsem\b|\bprimeiro\b|\bterceiro\b", " ", k)
    k = re.sub(r"\s+", " ", k).strip()
    if k in _CURSO_POR_CHAVE:
        nome, nivel = _CURSO_POR_CHAVE[k]
        return nome, nivel, semestre, trilha
    for apelido in _APELIDOS_ORDENADOS:
        if re.search(rf"\b{re.escape(apelido)}\b", k):
            nome, nivel = _CURSO_POR_CHAVE[apelido]
            return nome, nivel, semestre, trilha
    return "", "", semestre, trilha


# ---------------------------------------------------------------------------
# Projetos / mentorias
# ---------------------------------------------------------------------------

PLACEHOLDER_PROJETO = re.compile(
    r"^(sim|nao|n|ainda nao|ainda nao tem|ainda nao tem( um)? nome|nao tem( um)? nome( ainda)?|ainda nao possui|"
    r"nao possui|nao possui nome|nao tenho|ainda nao tenho|nao tenho nome|sem nome|projeto|nenhum|nenhuma|"
    r"estruturando|em construcao|em desenvolvimento|nao definido|a definir|ainda sem nome|nao sei|"
    r"nao ainda|ainda nao definido|tem|sim tem|possui|ideia|nao tem|ainda estou pensando)$"
)


def nome_projeto(v):
    """Limpa o nome do projeto. Retorna '' quando a resposta não é um nome."""
    s = texto(v).replace("\n", " ")
    if not s:
        return ""
    k = chave(s)
    if PLACEHOLDER_PROJETO.match(k) or len(k) <= 1:
        return ""
    # respostas negativas com explicação ("Não tenho um projeto", "Não tem ainda, mas...")
    if re.match(r"^(nao|ainda nao)\b(?! e )", k) and not re.search(r"\bnome e\b|se chama", k):
        return ""
    # "NOME DO PROJETO (WORKY) - descrição"
    m = re.match(r"^nome do projeto\s*\(([^)]+)\)", s, flags=re.I)
    if m:
        return m.group(1).strip()
    # "... Projeto : MMU"  /  "... nome é CloudNova"  /  "o nome do projeto é FindIt"
    m = re.search(r"projeto\s*:\s*(.+)$", s, flags=re.I) or \
        re.search(r"(?:nome(?: do projeto| da empresa)?|chama)\s+(?:[ée]|se)\s*[:\-]?\s*(.+)$", s, flags=re.I)
    if m:
        s = m.group(1)
    else:
        m = re.match(r"^(?:sim|tem)\b\s*[,.:;\-]?\s*(.+)$", s, flags=re.I)
        if m:
            s = m.group(1)
    s = s.strip(" .,;:-\"'()")
    s = re.sub(r"^possivelmente\s+", "", s, flags=re.I).strip(" .,;:-\"'()")
    if not s or PLACEHOLDER_PROJETO.match(chave(s)):
        return ""
    if len(s) > 120:  # resposta longa: é descrição, não nome
        return ""
    return s


def trl(v):
    m = re.search(r"trl\s*(\d)", chave(v))
    return int(m.group(1)) if m else None


def formato_mentoria(v):
    k = chave(v)
    if "online" in k:
        return "online"
    if "presencial" in k:
        return "presencial"
    return ""


def periodo(v):
    k = chave(v)
    for p in ("manha", "almoco", "tarde", "noite"):
        if k.startswith(p):
            return {"manha": "manhã", "almoco": "almoço"}.get(p, p)
    return "outro horário" if "fora" in k else ""


VINCULO_PROJETO_FACENS = [
    ("UPX", r"\bupx"), ("TCC", r"\btcc"), ("Desafio de Inovação", r"desafio|florestas"),
    ("PIEMP", r"piemp"), ("Startup Final Project", r"startup final"), ("Lince", r"lince"),
    ("Programa de Ideação/Pré-aceleração FACE", r"pre aceleracao|aceleracao de ideias|ideacao"),
    ("Internacionalização de Startups", r"internacionaliza"), ("Competição estudantil", r"formula sae|baja|competicao"),
]


def projeto_facens(v):
    """Classifica a resposta 'faz parte de algum projeto da Facens?' em etiquetas."""
    k = chave(v)
    if not k:
        return []
    tags = [nome for nome, rx in VINCULO_PROJETO_FACENS if re.search(rx, k)]
    if not tags and re.match(r"^(nao|nunca|ainda nao|por enquanto nao)", k):
        return ["Não"]
    return tags or ["Outro"]


COMO_SOUBE = [
    ("Redes sociais", r"instagram|linkedin|facebook|rede social|redes sociais|insta\b|bio do"),
    ("WhatsApp", r"whats|grupo"),
    ("E-mail", r"e mail|email|newsletter"),
    ("Professores/coordenadores", r"professor|coordenador|prof\b|docente|aula|curso de"),
    ("Equipe FACE", r"\bface\b|natalia|vitor|karla|regiane|trabalhei no face|monitor"),
    ("Indicação", r"indica|amig|filh|colega|alun|conhecid|recomend"),
    ("Eventos/palestras", r"evento|palestra|startup day|startapday|semana|feira"),
    ("Site/busca", r"site|google|busca|facens br"),
    ("Sebrae", r"sebrae|empretec"),
    ("Outro programa do FACE", r"internacionaliza|piemp|spark|start\b|wadhwani"),
]


def como_soube(v):
    k = chave(v)
    if not k:
        return []
    tags = [nome for nome, rx in COMO_SOUBE if re.search(rx, k)]
    return tags or ["Outro"]


def encaminhamentos(v):
    """Extrai os encaminhamentos da coluna 'ORIENTAÇÃO / PRÓXIMOS PASSOS'."""
    k = chave(v)
    if not k:
        return []
    saida = []
    for m in re.finditer(r"\bwf\s*(\d+)?\s*(ed|turma)?", k):
        saida.append(f"Wadhwani (WF) turma {m.group(1)}" if m.group(1) else "Wadhwani (WF)")
    if re.search(r"turma \d+ (da )?wf|turma \d+ wf", k):
        n = re.search(r"turma (\d+)", k).group(1)
        saida.append(f"Wadhwani (WF) turma {n}")
    regras = [("Spark (Sebrae)", r"spark"), ("Start Digital (Sebrae)", r"star[t]? digital|\bdigital\b"),
              ("Start Primeiras Vendas (Sebrae)", r"primeiras vendas"), ("PIEMP", r"piemp"),
              ("Sebrae", r"\bsebrae\b"), ("Shark Tank", r"shark"), ("Facens", r"^facens$"),
              ("Centelha", r"centelha"), ("Orientação", r"^orientacao$")]
    for nome, rx in regras:
        if re.search(rx, k) and nome not in saida:
            saida.append(nome)
    return list(dict.fromkeys(saida))


def mes_para_numero(v):
    k = chave(v)[:3]
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return meses.index(k) + 1 if k in meses else None


# ---------------------------------------------------------------------------
# Integrantes escritos em texto livre (TCC Connect, PIEMP)
# ---------------------------------------------------------------------------

def integrantes_texto(v):
    """
    Lê textos como 'Nome / Curso / RA / e-mail' (um por linha, ou separados por ',' '-' '/').
    Retorna lista de dicts com nome, curso, ra, email, telefone (o que for encontrado).
    """
    s = texto(v)
    if not s:
        return []
    linhas = [l for l in s.split("\n") if l.strip()]
    # várias linhas que parecem registros completos = uma pessoa por linha; senão, tudo é uma pessoa só
    completas = [l for l in linhas if "@" in l or re.search(r"(?<!\d)\d{6}(?!\d)", l)]
    blocos = linhas if len(linhas) > 1 and len(completas) == len(linhas) else [" / ".join(linhas)]
    pessoas = []
    for b in blocos:
        p = {"nome": "", "curso": "", "ra": "", "email": "", "telefone": "", "problema": ""}
        b = re.sub(r"https?://\S+|\S*lattes\S*", " ", b, flags=re.I)
        achados = re.findall(r"[\w.%+\-]+@[\w.\-]+\.[a-z]{2,}", b, flags=re.I)
        if achados:
            p["email"] = (emails(achados[0])[0] or [""])[0]
        b = re.sub(r"[\w.%+\-]+@[\w.\-]+\.[a-z]{2,}", " ", b, flags=re.I)
        fone = re.search(r"(?:\+?55\s*)?\(?\d{2}\)?\s*9?\s?\d{4}[\s\-.]?\d{4}(?!\d)", b)
        if fone:
            p["telefone"] = telefone(fone.group(0))[0]
            b = b.replace(fone.group(0), " ")
        m = re.search(r"\bra\s*:?\s*(\d+)", b, flags=re.I) or re.search(r"(?<!\d)(\d{6,7})(?!\d)", b)
        if m:
            if len(m.group(1)) == 6:
                p["ra"] = m.group(1)
            else:
                p["problema"] = f"RA fora do padrão: {m.group(1)}"
            b = b.replace(m.group(0), " ")
        partes = [x.strip(" :.") for x in re.split(r"\s*(?:/|;|\||,|\s+[-–]|[-–]\s+|-(?=\s*\d)|(?<=\d)\s*-)\s*", b)]
        for parte in partes:
            parte = re.sub(r"^(nome|ra|curso|e-?mail|whats(app)?|link)\b\s*:?\s*", "", parte, flags=re.I).strip(" :.-")
            if not parte or re.fullmatch(r"[\d\s\-()+]*", parte):
                continue
            if not p["curso"] and curso(parte)[0]:
                p["curso"] = parte
            elif not p["nome"] and re.search(r"[^\W\d_]{2,}\s+[^\W\d_]{2,}", parte):
                p["nome"] = nome_pessoa(parte)
        if p["nome"]:
            pessoas.append(p)
    return pessoas


# ---------------------------------------------------------------------------
# Cores usadas pela equipe para marcar status nas planilhas
# ---------------------------------------------------------------------------

LEGENDA_STATUS = ["Ainda não vi", "Realizado", "Não realizado", "Agendado", "Para agendar", "Para reagendar",
                  "Não respondeu"]

# legenda padrão das planilhas de mentoria (usada quando a aba não traz a legenda)
STATUS_POR_COR = {
    "00FF00": "realizado", "6AA84F": "realizado", "38761D": "realizado",
    "FF0000": "não realizado", "FFFF00": "agendado", "FF9900": "para agendar",
    "9900FF": "para reagendar", "FF00FF": "não respondeu",
}

CORES_IGNORADAS = {"FFFFFF", "000000", "F8F9FA", "EFEFEF"}


def nome_cor(rgb):
    """Nome simples de uma cor (para perguntar à equipe o que ela significa)."""
    if not rgb or rgb in CORES_IGNORADAS:
        return ""
    r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    claro = min(r, g, b) > 150
    if abs(r - g) < 12 and abs(g - b) < 12:
        return "cinza"
    if r >= g and r >= b:
        nome = "amarelo" if g > 200 and b < 120 else ("laranja" if g > 120 and b < 80 else
                                                      ("rosa/magenta" if b > g + 40 else "vermelho"))
    elif g >= r and g >= b:
        nome = "verde"
    else:
        nome = "roxo" if r > 120 else "azul"
    return f"{nome} claro" if claro and nome not in ("amarelo",) else nome
