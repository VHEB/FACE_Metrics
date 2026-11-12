"""
Testes da evolução de novembro/2026: validação de CPF, carga da base consolidada e
o fluxo pedido de mentoria → sessão no portal.

Rodar:  python manage.py test core
(usam dados fictícios — nenhum dado real do FACE)
"""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import (
    Evento, EventoParticipante, Mentoria, Participacao, PedidoMentoria, Pessoa, Projeto, validar_cpf,
)

CPF_VALIDO = "52998224725"  # CPF fictício de exemplo (dígitos verificadores corretos)


def base_ficticia():
    pessoa = lambda i, **k: {  # noqa: E731
        "id": f"P000{i}", "nome": f"Pessoa Teste {i}", "cpf": "", "ra": "", "rg": "", "email": f"p{i}@exemplo.com",
        "emails_alternativos": "", "telefone": "+5515999990000", "data_nascimento": None, "cep": "", "estado": "",
        "vinculo_atual": "Aluno(a)", "vinculos_declarados": "", "curso": "Engenharia de Computação",
        "nivel": "Graduação", "ano_formacao": None, "cnpj": "", "consentimento_lgpd": "", "data_consentimento": None,
        **k,
    }
    return {
        "Pessoas": [pessoa(1, cpf=CPF_VALIDO), pessoa(2, vinculo_atual="Comunidade externa", curso="", nivel="")],
        "Atividades": [
            {"id": "tcc-connect-2025-1", "tipo": "programa", "programa": "TCC Connect", "edicao": "2025.1",
             "nome": "TCC Connect 2025.1", "data_evento": None, "local": "", "inscricoes_de": "2024-12-01",
             "inscricoes_ate": "2025-03-01", "observacao": ""},
            {"id": "beauty-fair-2026", "tipo": "viagem", "programa": "Beauty Fair", "edicao": "2026",
             "nome": "Beauty Fair 2026", "data_evento": "2026-09-08", "local": "Expo Center Norte",
             "inscricoes_de": None, "inscricoes_ate": None, "observacao": ""},
        ],
        "Inscrições": [
            {"pessoa_id": "P0001", "atividade_id": "tcc-connect-2025-1", "data_inscricao": "2024-12-10",
             "papel": "líder", "status": "desistiu", "vinculo_na_inscricao": "Aluno(a)",
             "curso_na_inscricao": "Engenharia de Computação", "projeto_id": "J0001", "detalhes": "",
             "fonte": "teste"},
            {"pessoa_id": "P0002", "atividade_id": "beauty-fair-2026", "data_inscricao": "2026-08-01",
             "papel": "participante", "status": "ausente", "vinculo_na_inscricao": "", "curso_na_inscricao": "",
             "projeto_id": "", "detalhes": "", "fonte": "teste"},
        ],
        "Projetos": [{"id": "J0001", "nome": "Projeto X", "descricao": "", "desafio_atual": "", "area": "",
                      "ods": "", "empresa_parceira": "Empresa Y", "trl_inicial": 2, "trl_atual": 5,
                      "origens": "TCC Connect", "status": "desistiu", "link_entrega": "", "mentor_cientifico": "",
                      "observacao": ""}],
        "Integrantes": [{"projeto_id": "J0001", "pessoa_id": "P0001", "papel": "líder"}],
        "Pedidos de mentoria": [{
            "id": "M0001", "pessoa_id": "P0002", "projeto_id": "", "data_pedido": "2025-03-01", "ano": 2025,
            "origem": "Extensão", "turma_extensao": "Projeto Startup", "vinculo_no_pedido": "Aluno(a)",
            "curso_no_pedido": "", "nome_projeto_informado": "", "tematica": "Ideia", "desafio": "",
            "projeto_facens": "", "projeto_facens_texto": "", "trl": 1, "formato": "online", "periodo": "noite",
            "horario_alternativo": "", "como_soube": "", "como_soube_texto": "", "observacao": "", "anexo": "",
            "status": "realizado (sem sessão registrada)", "fonte": "teste"}],
        "Sessões de mentoria": [
            {"id": "S0001", "pessoa_id": "P0002", "pedido_id": "M0001", "projeto_id": "", "data": "2025-03-10",
             "horario": "19:00", "responsavel": "VH", "mentor": "Mentora Teste (T001)", "area": "Negócios",
             "encaminhamentos": "Spark (Sebrae)", "orientacao": "", "observacoes": "", "fonte": "teste"},
            {"id": "S0002", "pessoa_id": "P0002", "pedido_id": "M0001", "projeto_id": "", "data": "2025-04-10",
             "horario": "", "responsavel": "VH", "mentor": "", "area": "", "encaminhamentos": "",
             "orientacao": "", "observacoes": "", "fonte": "teste"},
        ],
        "Mentores": [{"id": "T001", "nome": "Mentora Teste", "email": "m@exemplo.com", "telefone": "",
                      "observacao": "", "areas": "Negócios", "sessoes": 1}],
    }


class ValidarCpfTest(TestCase):
    def test_cpf_valido(self):
        validar_cpf(CPF_VALIDO)

    def test_cpf_invalido(self):
        for ruim in ("52998224724", "11111111111", "123", "5299822472a"):
            with self.assertRaises(ValidationError):
                validar_cpf(ruim)


class CargaBaseConsolidadaTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.tmp.name) / "base.json"
        self.arquivo.write_text(json.dumps(base_ficticia()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def carregar(self, *extra):
        with override_settings(BASE_DIR=Path(self.tmp.name)):
            call_command("carregar_base_consolidada", str(self.arquivo), *extra, stdout=StringIO())

    def test_simulacao_nao_altera_nada(self):
        self.carregar()
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_carga_completa(self):
        self.carregar("--confirmar")
        self.assertEqual(Pessoa.objects.exclude(tipo_pessoa="mentor_parceiro").count(), 2)
        self.assertEqual(Pessoa.objects.get(codigo_importacao="P0001").cpf, CPF_VALIDO)

        participacao = Participacao.objects.get()
        self.assertEqual((participacao.papel, participacao.status), ("lider", "desistente"))
        self.assertEqual(participacao.edicao.ano, 2025)
        self.assertEqual(participacao.edicao.semestre, 1)

        projeto = Projeto.objects.get()
        self.assertEqual((projeto.status, projeto.estagio, projeto.categoria), ("desistiu", "mvp", "extensao_academica"))
        self.assertEqual(projeto.empresa_parceira.nome, "Empresa Y")
        self.assertEqual(list(projeto.edicoes.all()), [participacao.edicao])

        inscricao = EventoParticipante.objects.get()
        self.assertIs(inscricao.presente, False)
        self.assertEqual(inscricao.evento.tipo, "viagem")

        pedido = PedidoMentoria.objects.get()
        self.assertEqual((pedido.status, pedido.status_detalhe, pedido.origem, pedido.periodo),
                         ("realizado", "sem sessão registrada", "extensao", "noite"))
        sessoes = list(pedido.sessoes.order_by("data"))
        self.assertEqual([s.tipo for s in sessoes], ["diagnostico", "acompanhamento"])
        self.assertEqual(sessoes[0].mentor.nome, "Mentora Teste")
        self.assertEqual(list(sessoes[0].mentorados.values_list("codigo_importacao", flat=True)), ["P0002"])

    def test_recarregar_nao_duplica_e_restaurar_desfaz(self):
        self.carregar("--confirmar")
        self.carregar("--confirmar")
        self.assertEqual(Pessoa.objects.count(), 3)  # 2 pessoas + 1 mentora
        backups = sorted((Path(self.tmp.name) / "backups").glob("*.json"))
        self.assertEqual(len(backups), 2)
        with override_settings(BASE_DIR=Path(self.tmp.name)):
            call_command("carregar_base_consolidada", "--restaurar", str(backups[0]), "--confirmar",
                         stdout=StringIO())
        self.assertEqual(Pessoa.objects.count(), 0)  # o primeiro backup foi feito com o banco vazio


class FluxoPedidoSessaoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("equipe", password="x")
        self.client.force_login(self.user)
        self.pessoa = Pessoa.objects.create(nome="Pessoa Teste", tipo_pessoa="aluno")
        self.pedido = PedidoMentoria.objects.create(pessoa=self.pessoa, ano=2026, status="agendado")

    def test_registrar_sessao_marca_pedido_realizado(self):
        resp = self.client.get(f"/portal/mentorias/nova/?pedido={self.pedido.pk}")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post("/portal/mentorias/nova/", {
            "tipo": "diagnostico", "pedido": self.pedido.pk, "data": "2026-11-12", "mentorados": [self.pessoa.pk],
        })
        self.assertEqual(resp.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, "realizado")
        self.assertEqual(Mentoria.objects.get().pedido, self.pedido)

    def test_atualizar_status_do_pedido(self):
        resp = self.client.post(f"/portal/pedidos/{self.pedido.pk}/", {
            "status": "para_reagendar", "responsavel": self.user.pk, "observacao_interna": "remarcar",
        })
        self.assertEqual(resp.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual((self.pedido.status, self.pedido.responsavel), ("para_reagendar", self.user))

    def test_telas_abrem_sem_dados(self):
        for url in ("/portal/pedidos/", f"/portal/pedidos/{self.pedido.pk}/", "/portal/mentorias/",
                    f"/portal/pessoas/{self.pessoa.pk}/", "/portal/eventos/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        Evento.objects.create(nome="Palestra sem data", tipo="palestra")
        self.assertEqual(self.client.get("/portal/eventos/").status_code, 200)
