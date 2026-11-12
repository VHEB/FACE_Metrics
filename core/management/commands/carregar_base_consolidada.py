"""
Carrega no sistema a base consolidada das planilhas (base_consolidada_face.json,
gerada por consolidacao/consolidar.py).

Uso:
    python -X utf8 manage.py carregar_base_consolidada dados\\saida\\base_consolidada_face.json
    python -X utf8 manage.py carregar_base_consolidada dados\\saida\\base_consolidada_face.json --confirmar

Sem --confirmar é só simulação: mostra o que seria carregado e não altera nada.

Para desfazer uma carga (voltar ao backup feito automaticamente):
    python -X utf8 manage.py carregar_base_consolidada --restaurar backups\antes_da_carga_AAAAMMDD_HHMMSS.json --confirmar

Com --confirmar:
    1. salva um backup de todos os dados atuais em backups/ (para desfazer);
    2. dentro de UMA transação, apaga pessoas, projetos, mentorias, pedidos, participações,
       edições, eventos e cursos, e carrega a base consolidada. Se algo der errado, nada muda.
    Usuários/senhas, o catálogo de Programas e os Parceiros NÃO são apagados.

Enquanto as planilhas forem a fonte oficial, rode este comando sempre que reconsolidar.
Quando a equipe passar a cadastrar direto no sistema, ele deixa de ser usado.
"""

import collections
import json
import re
from datetime import date, datetime
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from core.models import (
    Curso, Edicao, Entrega, Evento, EventoParticipante, Mentoria, Parceiro, Participacao, PedidoMentoria,
    PerfilMentor, Pessoa, Programa, Projeto, ProjetoParticipante,
)

# ---------------------------------------------------------------------------
# Tradução dos textos da base consolidada para os códigos do sistema
# ---------------------------------------------------------------------------

VINCULO = {
    "Aluno(a)": "aluno", "Ex-aluno(a)": "ex_aluno", "Comunidade externa": "comunidade_externa",
    "Docente": "docente", "Colaborador(a)": "colaborador", "": "",
}
NIVEL = {"Graduação": "graduacao", "Pós-graduação": "pos"}
PAPEL_PARTICIPACAO = {"líder": "lider", "integrante": "integrante", "participante": "participante"}
STATUS_PARTICIPACAO = {
    "inscrito": "inscrito", "lista de espera": "lista_espera", "participou": "participou",
    "não participou": "nao_participou", "concluiu": "concluido", "desistiu": "desistente",
}
PRESENCA_EVENTO = {"presente": True, "participou": True, "ausente": False, "não participou": False}
PAPEL_PROJETO = {"responsável": "responsavel", "líder": "lider", "integrante": "integrante",
                 "participante": "integrante"}
STATUS_PROJETO = {"desistiu": "desistiu", "concluiu": "concluido"}
ORIGEM_PEDIDO = {"Programa de Mentorias": "programa_mentorias", "Extensão": "extensao"}
STATUS_PEDIDO = {
    "realizado": "realizado", "não realizado": "nao_realizado", "agendado": "agendado",
    "para agendar": "para_agendar", "para reagendar": "para_reagendar", "não respondeu": "nao_respondeu",
    "aguardando": "aguardando", "sem registro": "sem_registro",
}
PERIODO = {"manhã": "manha", "almoço": "almoco", "tarde": "tarde", "noite": "noite", "outro horário": "outro"}
TIPO_EVENTO = {"viagem": "viagem", "evento": "palestra"}

# programas da base consolidada que não estão no seed_programas
PROGRAMAS_NOVOS = {
    "PIEMP": ("piemp", "iniciacao", "Programa de Iniciação ao Empreendedorismo (bolsas CNPq)."),
    "Ideação Wadhwani (WF)": ("ideacao-wadhwani", "ideacao", ""),
}


def _data(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _hora(v):
    try:
        return datetime.strptime(v, "%H:%M").time() if v else None
    except ValueError:
        return None


def _estagio_por_trl(trl):
    """Aproximação do estágio a partir do TRL (1–3 ideação, 4–5 MVP, 6–7 validação, 8–9 tração)."""
    if trl is None:
        return "ideacao"
    return "ideacao" if trl <= 3 else "mvp" if trl <= 5 else "validacao" if trl <= 7 else "tracao"


def _fim_da_edicao(ano, semestre):
    if semestre == 1:
        return date(ano, 7, 31)
    return date(ano, 12, 31)


ORDEM_EXCLUSAO = [
    Entrega, EventoParticipante, Evento, Mentoria, PedidoMentoria, ProjetoParticipante, Participacao,
    Projeto, PerfilMentor, Pessoa, Edicao, Curso,
]


class Command(BaseCommand):
    help = "Carrega a base consolidada das planilhas (com backup automático e transação única)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", nargs="?", help="base_consolidada_face.json")
        parser.add_argument("--confirmar", action="store_true", help="Aplica de verdade (sem isso, só simula)")
        parser.add_argument("--restaurar", metavar="BACKUP", help="Volta os dados para um backup em backups/")

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if opts["restaurar"]:
            return self._restaurar(Path(opts["restaurar"]), opts["confirmar"])
        if not opts["arquivo"]:
            raise CommandError("Informe o arquivo base_consolidada_face.json.")
        caminho = Path(opts["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}. Rode antes o consolidacao/consolidar.py.")
        try:
            self.base = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"O arquivo não é um JSON válido: {exc}") from exc
        faltando = {"Pessoas", "Atividades", "Inscrições", "Projetos", "Integrantes", "Pedidos de mentoria",
                    "Sessões de mentoria", "Mentores"} - set(self.base)
        if faltando:
            raise CommandError(f"Este não parece ser o base_consolidada_face.json (faltam: {', '.join(faltando)}).")

        self.stdout.write(self.style.MIGRATE_HEADING("Hoje no sistema  →  depois da carga"))
        b = self.base
        atividades = b["Atividades"]
        previsto = [
            ("Pessoas", Pessoa.objects.count(), len(b["Pessoas"]) + len(b["Mentores"])),
            ("Projetos", Projeto.objects.count(), len(b["Projetos"])),
            ("Pedidos de mentoria", PedidoMentoria.objects.count(), len(b["Pedidos de mentoria"])),
            ("Mentorias (sessões)", Mentoria.objects.count(), len(b["Sessões de mentoria"])),
            ("Edições de programas", Edicao.objects.count(), sum(a["tipo"] == "programa" for a in atividades)),
            ("Participações em programas", Participacao.objects.count(),
             sum(1 for i in b["Inscrições"] if self._tipo_ativ(i["atividade_id"]) == "programa")),
            ("Viagens e eventos", Evento.objects.count(), sum(a["tipo"] != "programa" for a in atividades)),
            ("Inscrições em viagens/eventos", EventoParticipante.objects.count(),
             sum(1 for i in b["Inscrições"] if self._tipo_ativ(i["atividade_id"]) != "programa")),
        ]
        for nome, hoje, depois in previsto:
            self.stdout.write(f"  {nome:<32} {hoje:>6}  →  {depois:>6}")

        if not opts["confirmar"]:
            self.stdout.write(self.style.WARNING(
                "\nSimulação: nada foi alterado. Para carregar de verdade, rode de novo com --confirmar."))
            return

        backup = self._backup()
        self.stdout.write(f"\nBackup dos dados atuais: {backup}")
        with transaction.atomic():
            for modelo in ORDEM_EXCLUSAO:
                modelo.objects.all().delete()
            self._carregar()
        self.stdout.write(self.style.SUCCESS("Base consolidada carregada."))
        for k, v in self.contagem.items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write(f"\nPara desfazer: python -X utf8 manage.py carregar_base_consolidada "
                          f"--restaurar {backup} --confirmar")

    def _restaurar(self, backup, confirmar):
        if not backup.exists():
            raise CommandError(f"Backup não encontrado: {backup}")
        if not confirmar:
            self.stdout.write(self.style.WARNING(
                f"Simulação: os dados atuais seriam trocados pelo backup {backup.name}. Rode com --confirmar."))
            return
        with transaction.atomic():
            for modelo in ORDEM_EXCLUSAO:
                modelo.objects.all().delete()
            call_command("loaddata", str(backup), verbosity=0)
        self.stdout.write(self.style.SUCCESS(f"Dados restaurados a partir de {backup.name}."))

    def _tipo_ativ(self, aid):
        return next((a["tipo"] for a in self.base["Atividades"] if a["id"] == aid), "")

    def _backup(self):
        pasta = Path(settings.BASE_DIR) / "backups"
        pasta.mkdir(exist_ok=True)
        base = f"antes_da_carga_{datetime.now():%Y%m%d_%H%M%S}"
        destino, n = pasta / f"{base}.json", 1
        while destino.exists():  # nunca sobrescreve um backup
            n += 1
            destino = pasta / f"{base}_{n}.json"
        buf = StringIO()
        call_command("dumpdata", "core", indent=1, stdout=buf)
        destino.write_text(buf.getvalue(), encoding="utf-8")
        return destino

    # ------------------------------------------------------------------
    def _carregar(self):
        b = self.base
        self.contagem = collections.Counter()
        self.cursos = {}

        # pessoas
        self.pessoas = {}
        for p in b["Pessoas"]:
            obj = Pessoa(
                nome=p["nome"][:200], cpf=p["cpf"] or None, rg=p["rg"][:20], ra=p["ra"][:20],
                email=p["email"][:254], emails_alternativos=p["emails_alternativos"],
                telefone=p["telefone"][:20], tipo_pessoa=VINCULO.get(p["vinculo_atual"], ""),
                data_nascimento=_data(p["data_nascimento"]), cep=p["cep"], estado=p["estado"][:2],
                curso=self._curso(p["curso"], NIVEL.get(p["nivel"])), ano_formacao=p["ano_formacao"],
                cnpj=p["cnpj"], consentimento_lgpd=p["consentimento_lgpd"] == "Sim",
                data_consentimento=_data(p["data_consentimento"]), codigo_importacao=p["id"],
            )
            self.pessoas[p["id"]] = obj
        Pessoa.objects.bulk_create(self.pessoas.values())
        self.contagem["Pessoas"] = len(self.pessoas)

        # mentores voluntários
        self.mentores = {}
        for m in b["Mentores"]:
            pessoa = Pessoa.objects.create(nome=m["nome"], email=m["email"], telefone=m["telefone"][:20],
                                           tipo_pessoa="mentor_parceiro", codigo_importacao=m["id"])
            PerfilMentor.objects.create(pessoa=pessoa, areas=m["areas"][:300], bio=m["observacao"])
            self.mentores[m["id"]] = pessoa
        self.contagem["Mentores"] = len(self.mentores)

        # programas/edições e viagens/eventos
        self.edicoes, self.eventos = {}, {}
        for a in b["Atividades"]:
            if a["tipo"] == "programa":
                self.edicoes[a["id"]] = self._edicao(a)
            else:
                self.eventos[a["id"]] = Evento.objects.create(
                    nome=a["nome"], tipo=TIPO_EVENTO.get(a["tipo"], "outro"), data=_data(a["data_evento"]),
                    local=a["local"], observacoes=a["observacao"],
                    inscricoes_inicio=_data(a["inscricoes_de"]), inscricoes_fim=_data(a["inscricoes_ate"]),
                )
        self.contagem["Edições de programas"] = len(self.edicoes)
        self.contagem["Viagens e eventos"] = len(self.eventos)

        # projetos
        self.projetos = {}
        for j in b["Projetos"]:
            empresa = None
            if j["empresa_parceira"]:
                empresa, _ = Parceiro.objects.get_or_create(nome=j["empresa_parceira"][:150])
            self.projetos[j["id"]] = Projeto(
                nome=j["nome"][:200], descricao=j["descricao"], desafio_atual=j["desafio_atual"],
                area=j["area"][:100], ods=j["ods"][:200], empresa_parceira=empresa,
                categoria="extensao_academica" if "TCC Connect" in j["origens"] else "",
                trl_inicial=j["trl_inicial"], trl_atual=j["trl_atual"], estagio=_estagio_por_trl(j["trl_atual"]),
                status=STATUS_PROJETO.get(j["status"], "ativo"), origens=j["origens"][:300],
                link_entrega=j["link_entrega"][:500], mentor_cientifico=j["mentor_cientifico"][:200],
                observacoes=j["observacao"], codigo_importacao=j["id"],
            )
        Projeto.objects.bulk_create(self.projetos.values())
        self.contagem["Projetos"] = len(self.projetos)
        ProjetoParticipante.objects.bulk_create([
            ProjetoParticipante(projeto=self.projetos[x["projeto_id"]], pessoa=self.pessoas[x["pessoa_id"]],
                                papel=PAPEL_PROJETO.get(x["papel"], "integrante"))
            for x in b["Integrantes"]
        ])
        self.contagem["Integrantes de projetos"] = len(b["Integrantes"])

        # inscrições
        participacoes, inscricoes = [], []
        edicoes_do_projeto = collections.defaultdict(set)
        for i in b["Inscrições"]:
            comum = dict(
                pessoa=self.pessoas[i["pessoa_id"]], vinculo_na_inscricao=VINCULO.get(i["vinculo_na_inscricao"], ""),
                curso_na_inscricao=self._curso(i["curso_na_inscricao"]), detalhes=i["detalhes"],
                origem=i["fonte"][:250],
            )
            if i["atividade_id"] in self.edicoes:
                edicao = self.edicoes[i["atividade_id"]]
                projeto = self.projetos.get(i["projeto_id"])
                participacoes.append(Participacao(
                    edicao=edicao, papel=PAPEL_PARTICIPACAO.get(i["papel"], "participante"),
                    status=STATUS_PARTICIPACAO.get(i["status"], "inscrito"),
                    data_entrada=_data(i["data_inscricao"]), projeto=projeto, **comum,
                ))
                if projeto:
                    edicoes_do_projeto[projeto.pk].add(edicao.pk)
            else:
                inscricoes.append(EventoParticipante(
                    evento=self.eventos[i["atividade_id"]], presente=PRESENCA_EVENTO.get(i["status"]),
                    data_inscricao=_data(i["data_inscricao"]), **comum,
                ))
        Participacao.objects.bulk_create(participacoes)
        EventoParticipante.objects.bulk_create(inscricoes)
        self.contagem["Participações em programas"] = len(participacoes)
        self.contagem["Inscrições em viagens/eventos"] = len(inscricoes)
        Ligacao = Projeto.edicoes.through
        Ligacao.objects.bulk_create([Ligacao(projeto_id=pj, edicao_id=ed)
                                     for pj, eds in edicoes_do_projeto.items() for ed in eds])

        # pedidos de mentoria
        self.pedidos = {}
        for p in b["Pedidos de mentoria"]:
            status_txt = p["status"]
            detalhe = re.search(r"\((.+)\)", status_txt)
            self.pedidos[p["id"]] = PedidoMentoria(
                pessoa=self.pessoas[p["pessoa_id"]], projeto=self.projetos.get(p["projeto_id"]),
                data_pedido=_data(p["data_pedido"]), ano=p["ano"], origem=ORIGEM_PEDIDO.get(p["origem"], "portal"),
                turma_extensao=p["turma_extensao"][:100],
                status=STATUS_PEDIDO.get(re.sub(r"\s*\(.*\)", "", status_txt), "sem_registro"),
                status_detalhe=detalhe.group(1)[:100] if detalhe else "",
                vinculo_no_pedido=VINCULO.get(p["vinculo_no_pedido"], ""),
                curso_no_pedido=self._curso(p["curso_no_pedido"]),
                nome_projeto_informado=p["nome_projeto_informado"][:300], tematica=p["tematica"],
                desafio=p["desafio"], projeto_facens=p["projeto_facens"][:200],
                projeto_facens_texto=p["projeto_facens_texto"], trl=p["trl"], formato=p["formato"],
                periodo=PERIODO.get(p["periodo"], ""), horario_alternativo=p["horario_alternativo"][:300],
                como_soube=p["como_soube"][:200], como_soube_texto=p["como_soube_texto"],
                observacao=p["observacao"], anexo=p["anexo"][:500], origem_registro=p["fonte"][:250],
                codigo_importacao=p["id"],
            )
        PedidoMentoria.objects.bulk_create(self.pedidos.values())
        self.contagem["Pedidos de mentoria"] = len(self.pedidos)

        # sessões (a primeira sessão de cada pedido é o diagnóstico)
        primeira = {}
        for s in sorted(b["Sessões de mentoria"], key=lambda s: s["data"] or "9999"):
            if s["pedido_id"] and s["pedido_id"] not in primeira:
                primeira[s["pedido_id"]] = s["id"]
        sessoes = []
        for s in b["Sessões de mentoria"]:
            pedido = self.pedidos.get(s["pedido_id"])
            projeto = self.projetos.get(s["projeto_id"])
            mentor_id = re.search(r"\((T\d+)\)", s["mentor"] or "")
            tema = (projeto.nome if projeto else "") or (pedido.tematica if pedido else "") or s["area"]
            sessao = Mentoria(
                mentor=self.mentores.get(mentor_id.group(1)) if mentor_id else None,
                tipo="diagnostico" if primeira.get(s["pedido_id"]) == s["id"] else "acompanhamento",
                projeto=projeto, pedido=pedido, data=_data(s["data"]), horario=_hora(s["horario"]),
                duracao_minutos=None, tema=tema[:200], observacoes=s["observacoes"],
                responsavel=s["responsavel"][:60], area=s["area"][:150], orientacao=s["orientacao"],
                encaminhamentos=s["encaminhamentos"][:300], origem_registro=s["fonte"][:250],
                codigo_importacao=s["id"],
            )
            sessao._mentorado = self.pessoas[s["pessoa_id"]]
            sessoes.append(sessao)
        Mentoria.objects.bulk_create(sessoes)
        Mentorados = Mentoria.mentorados.through
        Mentorados.objects.bulk_create([Mentorados(mentoria_id=s.pk, pessoa_id=s._mentorado.pk) for s in sessoes])
        self.contagem["Mentorias (sessões)"] = len(sessoes)

    # ------------------------------------------------------------------
    def _curso(self, nome, nivel=None):
        if not nome:
            return None
        if nivel is None:
            nivel = "pos" if re.match(r"(Pós|MBA|Especialização)", nome) else "graduacao"
        chave = (nome, nivel)
        if chave not in self.cursos:
            self.cursos[chave], _ = Curso.objects.get_or_create(nome=nome[:150], nivel=nivel)
        return self.cursos[chave]

    def _edicao(self, a):
        programa = Programa.objects.filter(nome__iexact=a["programa"]).first()
        if not programa:
            slug, tipo, descricao = PROGRAMAS_NOVOS.get(a["programa"], (slugify(a["programa"]), "evento_capacitacao", ""))
            programa = Programa.objects.filter(slug=slug).first() or Programa.objects.create(
                nome=a["programa"], slug=slug, tipo=tipo, descricao=descricao)
        m = re.match(r"(\d{4})(?:\.(\d))?", a["edicao"])
        ano, semestre = int(m.group(1)), int(m.group(2)) if m.group(2) else None
        concluida = _fim_da_edicao(ano, semestre) < date.today()
        edicao, _ = Edicao.objects.update_or_create(
            programa=programa, ano=ano, semestre=semestre,
            defaults=dict(
                status="concluida" if concluida else "em_andamento",
                inscricoes_inicio=_data(a["inscricoes_de"]), inscricoes_fim=_data(a["inscricoes_ate"]),
                observacoes="\n".join(x for x in (a["observacao"], a["edicao"] if "—" in a["edicao"] else "") if x),
            ),
        )
        return edicao
