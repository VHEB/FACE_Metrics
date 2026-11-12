"""
Modelos do FACE Metrics.

Novembro/2026 — evolução para receber a base consolidada das planilhas:
    + PedidoMentoria  (o pedido feito no formulário, com status de atendimento)
    + Mentoria        passa a ser a SESSÃO realizada, ligada ao pedido
    + PerfilMentor    (mentores voluntários / parceiros)
    + Evento          ganha o tipo "viagem", vagas e período de inscrição;
                      EventoParticipante ganha status da inscrição (a presença continua em `presente`)
    + campos novos em Pessoa, Projeto, Edição e Participação

Desenho geral:
    Programa (catálogo fixo: Spark, Start, Internacionalização, CRIE Games,
              Power Girl, TCC Connect, Mentoria em Empreendedorismo, Sebrae Aqui...)
        -> Edicao (instância anual/semestral de um Programa: "Spark 2025.2")
            -> Participacao (liga Pessoa <-> Edicao, com papel e status)
            -> Mentoria (sessões, ligadas opcionalmente a uma Edicao/Projeto)
            -> Evento (visitas técnicas, palestras, etc., ligados opcionalmente a uma Edicao)

    Pessoa é o cadastro único de quem passa pelo FACE: aluno, ex-aluno,
    comunidade externa, docente, colaborador ou mentor parceiro.

    Projeto agrupa uma ideia/startup que pode atravessar várias Edições
    (ex.: nasce no Spark e depois entra no Start).
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


def validar_cpf(valor):
    """CPF com 11 dígitos e dígitos verificadores corretos."""
    if not valor:
        return
    if len(valor) != 11 or not valor.isdigit() or len(set(valor)) == 1:
        raise ValidationError("CPF inválido: informe 11 dígitos, sem pontuação.")
    for n in (9, 10):
        soma = sum(int(valor[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(valor[n]):
            raise ValidationError("CPF inválido: dígito verificador não confere.")


TRL_VALIDADORES = [MinValueValidator(1), MaxValueValidator(9)]


class TimeStampedModel(models.Model):
    """Base abstrata para auditoria simples de criação/alteração."""

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Catálogos de apoio
# ---------------------------------------------------------------------------

class Parceiro(TimeStampedModel):
    """Instituições parceiras: Sebrae, CCBEU, FCBB, Parque Tecnológico de Sorocaba etc."""

    nome = models.CharField(max_length=150, unique=True)
    site = models.URLField(blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Parceiro"
        verbose_name_plural = "Parceiros"

    def __str__(self):
        return self.nome


class Curso(TimeStampedModel):
    """Cursos da UniFacens (graduação/pós), usados no cadastro de Pessoa."""

    NIVEL_CHOICES = [
        ("graduacao", "Graduação"),
        ("pos", "Pós-graduação"),
    ]

    nome = models.CharField(max_length=150)
    nivel = models.CharField(max_length=20, choices=NIVEL_CHOICES, default="graduacao")

    class Meta:
        ordering = ["nome"]
        unique_together = ("nome", "nivel")

    def __str__(self):
        return f"{self.nome} ({self.get_nivel_display()})"


class Programa(TimeStampedModel):
    """
    Catálogo FIXO de programas do FACE. Não se cria um Programa novo com
    frequência — o que muda ano a ano são as Edições dele.
    """

    TIPO_CHOICES = [
        ("ideacao", "Ideação"),
        ("pre_aceleracao", "Pré-aceleração"),
        ("internacionalizacao", "Internacionalização"),
        ("mentoria", "Mentoria contínua"),
        ("inovacao_aberta", "Inovação aberta"),
        ("evento_capacitacao", "Evento / Capacitação"),
        ("atendimento", "Atendimento (ex.: Sebrae Aqui)"),
        ("iniciacao", "Iniciação ao empreendedorismo (ex.: PIEMP)"),
    ]

    nome = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(unique=True)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    descricao = models.TextField(blank=True)
    parceiros = models.ManyToManyField(Parceiro, blank=True, related_name="programas")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Programa"
        verbose_name_plural = "Programas"

    def __str__(self):
        return self.nome


class Edicao(TimeStampedModel):
    """
    Uma instância concreta de um Programa em um período: "Spark 2025.2",
    "Power Girl 2026", "Start 2025.1". É esta entidade que alimenta os
    filtros e dashboards por ano/semestre.
    """

    STATUS_CHOICES = [
        ("planejada", "Planejada"),
        ("inscricoes_abertas", "Inscrições abertas"),
        ("em_andamento", "Em andamento"),
        ("concluida", "Concluída"),
        ("cancelada", "Cancelada"),
    ]

    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name="edicoes")
    ano = models.PositiveSmallIntegerField()
    semestre = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Deixe em branco se o programa tiver periodicidade anual (ex.: Power Girl).",
    )
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="planejada")
    vagas = models.PositiveIntegerField(null=True, blank=True)
    observacoes = models.TextField(blank=True)

    # vitrine pública (portal externo)
    inscricoes_inicio = models.DateField("início das inscrições", null=True, blank=True)
    inscricoes_fim = models.DateField("fim das inscrições", null=True, blank=True)
    descricao_publica = models.TextField(blank=True, help_text="Texto exibido na vitrine pública.")
    publicada = models.BooleanField("publicada na vitrine", default=False)

    class Meta:
        ordering = ["-ano", "-semestre"]
        unique_together = ("programa", "ano", "semestre")
        verbose_name = "Edição"
        verbose_name_plural = "Edições"

    def __str__(self):
        periodo = f"{self.ano}.{self.semestre}" if self.semestre else str(self.ano)
        return f"{self.programa.nome} - {periodo}"

    @property
    def inscricoes_abertas(self):
        hoje = date.today()
        return bool(self.inscricoes_inicio and self.inscricoes_fim
                    and self.inscricoes_inicio <= hoje <= self.inscricoes_fim)


# ---------------------------------------------------------------------------
# Pessoas e participação
# ---------------------------------------------------------------------------

class Pessoa(TimeStampedModel):
    """
    Cadastro único de qualquer pessoa que passou pelo FACE.

    Observação LGPD: CPF é opcional (nem toda pessoa da comunidade externa
    vai fornecer) e deve ser tratado como dado sensível — evitar logs,
    considerar criptografia em repouso via campo customizado ou
    django-cryptography/django-fernet-fields antes de ir pra produção.
    """

    TIPO_CHOICES = [
        ("aluno", "Aluno(a)"),
        ("ex_aluno", "Ex-aluno(a)"),
        ("comunidade_externa", "Comunidade externa"),
        ("docente", "Docente"),
        ("colaborador", "Colaborador(a) Facens"),
        ("mentor_parceiro", "Mentor parceiro"),
    ]

    nome = models.CharField(max_length=200)
    cpf = models.CharField(
        "CPF", max_length=11, validators=[validar_cpf],
        blank=True, null=True, unique=True,
        help_text="Somente números. Obrigatório nos cadastros novos (pedido desde meados de 2025). "
                  "Campo sensível — tratar com cuidado (LGPD).",
    )
    rg = models.CharField(max_length=20, blank=True, help_text="Campo sensível — tratar com cuidado (LGPD).")
    email = models.EmailField(blank=True)
    emails_alternativos = models.TextField("outros e-mails", blank=True,
                                           help_text="E-mails usados em outros formulários, separados por vírgula.")
    telefone = models.CharField(max_length=20, blank=True, help_text="Formato +55DDNNNNNNNNN.")
    tipo_pessoa = models.CharField("vínculo atual", max_length=25, choices=TIPO_CHOICES, blank=True,
                                   help_text="O vínculo muda com o tempo; o de cada inscrição fica na inscrição.")
    data_nascimento = models.DateField(null=True, blank=True)

    curso = models.ForeignKey(
        Curso, on_delete=models.SET_NULL, null=True, blank=True, related_name="pessoas",
        help_text="Preencher apenas se aluno(a) ou ex-aluno(a).",
    )
    ra = models.CharField("RA", max_length=20, blank=True)
    semestre_ingresso = models.CharField(max_length=10, blank=True, help_text="Ex.: 2023.1")
    ano_formacao = models.PositiveSmallIntegerField("ano de formação", null=True, blank=True,
                                                    help_text="Para ex-alunos.")

    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True, help_text="Empresa da pessoa, se informada.")
    observacoes = models.TextField("observações", blank=True)
    codigo_importacao = models.CharField(
        "código na base consolidada", max_length=12, blank=True, db_index=True,
        help_text="ID gerado pela consolidação das planilhas (ex.: P0001). Só para rastrear a origem.",
    )

    consentimento_lgpd = models.BooleanField(
        default=False,
        help_text="Marcar quando houver consentimento explícito para tratamento dos dados.",
    )
    data_consentimento = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Pessoa"
        verbose_name_plural = "Pessoas"

    def __str__(self):
        return self.nome


class Participacao(TimeStampedModel):
    """Liga uma Pessoa a uma Edição específica de um Programa."""

    PAPEL_CHOICES = [
        ("participante", "Participante"),
        ("lider", "Líder do grupo"),
        ("integrante", "Integrante do grupo"),
        ("mentor", "Mentor(a)"),
        ("mentorado", "Mentorado(a)"),
        ("organizador", "Organizador(a)"),
        ("palestrante", "Palestrante"),
    ]

    STATUS_CHOICES = [
        ("inscrito", "Inscrito(a)"),
        ("lista_espera", "Lista de espera"),
        ("em_andamento", "Em andamento"),
        ("participou", "Participou"),
        ("nao_participou", "Não participou"),
        ("concluido", "Concluído"),
        ("desistente", "Desistente"),
    ]

    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="participacoes")
    edicao = models.ForeignKey(Edicao, on_delete=models.CASCADE, related_name="participacoes")
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES, default="participante")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inscrito")
    data_entrada = models.DateField("data de inscrição", null=True, blank=True)
    data_saida = models.DateField(null=True, blank=True)
    projeto = models.ForeignKey("Projeto", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="participacoes")
    vinculo_na_inscricao = models.CharField(max_length=25, choices=Pessoa.TIPO_CHOICES, blank=True,
                                            help_text="Vínculo declarado no momento da inscrição.")
    curso_na_inscricao = models.ForeignKey(Curso, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="+")
    detalhes = models.TextField(blank=True)
    origem = models.CharField(max_length=250, blank=True, help_text="Planilha/linha de onde veio o registro.")

    class Meta:
        unique_together = ("pessoa", "edicao", "papel")
        ordering = ["-edicao__ano", "pessoa__nome"]
        verbose_name = "Participação"
        verbose_name_plural = "Participações"

    def __str__(self):
        return f"{self.pessoa.nome} em {self.edicao} ({self.get_papel_display()})"


# ---------------------------------------------------------------------------
# Projetos
# ---------------------------------------------------------------------------

class Projeto(TimeStampedModel):
    """
    Uma ideia/startup, que pode atravessar múltiplas Edições
    (ex.: nasce no Spark 2025.1 e evolui para o Start 2025.2).
    """

    ESTAGIO_CHOICES = [
        ("ideacao", "Ideação"),
        ("mvp", "MVP"),
        ("validacao", "Validação"),
        ("tracao", "Tração"),
        ("encerrado", "Encerrado"),
    ]

    CATEGORIA_CHOICES = [
        ("startup_digital", "Startup Digital"),
        ("startup_cientifica", "Startup Científica/DeepTech"),
        ("negocio_impacto", "Negócio de Impacto Social"),
        ("extensao_academica", "Extensão/Aplicação Acadêmica (ex.: TCC Connect)"),
        ("outro", "Outro"),
    ]

    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    area = models.CharField(max_length=100, blank=True, help_text="Ex.: Saúde, Educação, Fintech...")
    categoria = models.CharField(
        max_length=30, choices=CATEGORIA_CHOICES, blank=True,
        help_text="Usado para filtros/dashboards. Lista fácil de ajustar depois.",
    )
    estagio = models.CharField(max_length=20, choices=ESTAGIO_CHOICES, default="ideacao")
    edicoes = models.ManyToManyField(Edicao, blank=True, related_name="projetos")
    empresa_parceira = models.ForeignKey(
        Parceiro, on_delete=models.SET_NULL, null=True, blank=True, related_name="desafios_propostos",
        help_text="Preencher quando o projeto for um desafio proposto por uma empresa parceira (ex.: TCC Connect).",
    )

    STATUS_CHOICES = [
        ("ativo", "Ativo"),
        ("concluido", "Concluído"),
        ("desistiu", "Desistiu / encerrado"),
    ]

    desafio_atual = models.TextField(blank=True)
    trl_inicial = models.PositiveSmallIntegerField("TRL inicial", null=True, blank=True, validators=TRL_VALIDADORES)
    trl_atual = models.PositiveSmallIntegerField("TRL atual", null=True, blank=True, validators=TRL_VALIDADORES)
    ods = models.CharField("ODS", max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativo")
    origens = models.CharField(max_length=300, blank=True,
                               help_text="Onde o projeto apareceu (mentoria, PIEMP, TCC Connect...).")
    link_entrega = models.CharField(max_length=500, blank=True)
    mentor_cientifico = models.CharField("mentor científico", max_length=200, blank=True)
    observacoes = models.TextField("observações", blank=True)
    codigo_importacao = models.CharField("código na base consolidada", max_length=12, blank=True, db_index=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

    def __str__(self):
        return self.nome


class ProjetoParticipante(TimeStampedModel):
    """Quem faz parte de um Projeto (fundador, colaborador etc.)."""

    PAPEL_CHOICES = [
        ("fundador", "Fundador(a)"),
        ("responsavel", "Responsável"),
        ("lider", "Líder"),
        ("integrante", "Integrante"),
        ("colaborador", "Colaborador(a)"),
    ]

    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="integrantes")
    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="projetos_participados")
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES, default="fundador")

    class Meta:
        unique_together = ("projeto", "pessoa")
        verbose_name = "Integrante do projeto"
        verbose_name_plural = "Integrantes do projeto"

    def __str__(self):
        return f"{self.pessoa.nome} - {self.projeto.nome}"


# ---------------------------------------------------------------------------
# Mentorias e eventos
# ---------------------------------------------------------------------------

class PerfilMentor(TimeStampedModel):
    """Dados de mentor de uma Pessoa (voluntário, parceiro, docente)."""

    pessoa = models.OneToOneField(Pessoa, on_delete=models.CASCADE, related_name="perfil_mentor")
    organizacao = models.CharField("organização", max_length=200, blank=True)
    areas = models.CharField("áreas de mentoria", max_length=300, blank=True)
    bio = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    exibir_na_vitrine = models.BooleanField(default=False)

    class Meta:
        ordering = ["pessoa__nome"]
        verbose_name = "Mentor"
        verbose_name_plural = "Mentores"

    def __str__(self):
        return self.pessoa.nome


class PedidoMentoria(TimeStampedModel):
    """
    O pedido de mentoria feito no formulário (Programa de Mentorias, Extensão ou,
    no futuro, o portal público). As sessões realizadas ficam em Mentoria, ligadas ao pedido.
    """

    ORIGEM_CHOICES = [
        ("programa_mentorias", "Programa de Mentorias"),
        ("extensao", "Extensão"),
        ("portal", "Portal público"),
    ]
    STATUS_CHOICES = [
        ("aguardando", "Aguardando triagem"),
        ("para_agendar", "Para agendar"),
        ("agendado", "Agendado"),
        ("para_reagendar", "Para reagendar"),
        ("realizado", "Realizado"),
        ("nao_realizado", "Não realizado"),
        ("nao_respondeu", "Não respondeu"),
        ("sem_registro", "Sem registro"),
    ]
    FORMATO_CHOICES = [("online", "Online"), ("presencial", "Presencial")]
    PERIODO_CHOICES = [("manha", "Manhã"), ("almoco", "Almoço"), ("tarde", "Tarde"), ("noite", "Noite"),
                       ("outro", "Outro horário")]

    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="pedidos_mentoria")
    projeto = models.ForeignKey("Projeto", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="pedidos_mentoria")
    data_pedido = models.DateField("data do pedido", null=True, blank=True)
    ano = models.PositiveSmallIntegerField(db_index=True)
    origem = models.CharField(max_length=25, choices=ORIGEM_CHOICES, default="programa_mentorias")
    turma_extensao = models.CharField("turma da extensão", max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aguardando", db_index=True)
    status_detalhe = models.CharField("detalhe do status", max_length=100, blank=True,
                                      help_text='Ex.: "sem sessão registrada" quando a planilha marcou realizado.')
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="responsável", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="pedidos_mentoria",
                                    help_text="Quem da equipe cuida do pedido.")

    # o que a pessoa respondeu
    vinculo_no_pedido = models.CharField("vínculo no pedido", max_length=25, choices=Pessoa.TIPO_CHOICES, blank=True)
    curso_no_pedido = models.ForeignKey(Curso, verbose_name="curso no pedido", on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name="+")
    nome_projeto_informado = models.CharField("nome do projeto (resposta)", max_length=300, blank=True)
    tematica = models.TextField("temática", blank=True)
    desafio = models.TextField(blank=True)
    projeto_facens = models.CharField("ligado a projeto Facens", max_length=200, blank=True)
    projeto_facens_texto = models.TextField("ligado a projeto Facens (resposta)", blank=True)
    trl = models.PositiveSmallIntegerField("TRL", null=True, blank=True, validators=TRL_VALIDADORES)
    formato = models.CharField(max_length=15, choices=FORMATO_CHOICES, blank=True)
    periodo = models.CharField("período preferido", max_length=10, choices=PERIODO_CHOICES, blank=True)
    horario_alternativo = models.CharField("horário alternativo", max_length=300, blank=True)
    como_soube = models.CharField("como soube", max_length=200, blank=True)
    como_soube_texto = models.TextField("como soube (resposta)", blank=True)
    observacao = models.TextField("observação", blank=True)
    anexo = models.CharField(max_length=500, blank=True)
    observacao_interna = models.TextField("observação interna", blank=True,
                                          help_text="Anotações da equipe (não visíveis ao solicitante).")

    origem_registro = models.CharField("origem do registro", max_length=250, blank=True,
                                       help_text="Planilha/linha de onde veio.")
    codigo_importacao = models.CharField("código na base consolidada", max_length=12, blank=True, db_index=True)

    class Meta:
        ordering = ["-data_pedido", "-ano"]
        verbose_name = "Pedido de mentoria"
        verbose_name_plural = "Pedidos de mentoria"

    def __str__(self):
        quando = f"{self.data_pedido:%d/%m/%Y}" if self.data_pedido else str(self.ano)
        return f"Pedido de {self.pessoa.nome} ({quando})"


class Mentoria(TimeStampedModel):
    """Registro de uma SESSÃO de mentoria realizada (ligada ao pedido, quando houver)."""

    TIPO_CHOICES = [
        ("diagnostico", "Diagnóstico (triagem inicial)"),
        ("acompanhamento", "Acompanhamento"),
        ("outro", "Outro"),
    ]

    mentor = models.ForeignKey(
        Pessoa, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentorias_realizadas",
        limit_choices_to={"tipo_pessoa__in": ["mentor_parceiro", "docente", "colaborador"]},
        help_text="Deixe em branco quando o mentor não estiver identificado no registro histórico.",
    )
    mentorados = models.ManyToManyField(Pessoa, related_name="mentorias_recebidas")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="acompanhamento")
    edicao = models.ForeignKey(
        Edicao, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentorias",
    )
    projeto = models.ForeignKey(
        Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentorias",
    )
    pedido = models.ForeignKey(PedidoMentoria, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="sessoes")
    data = models.DateField(null=True)
    horario = models.TimeField("horário", null=True, blank=True)
    duracao_minutos = models.PositiveIntegerField("duração (min)", default=60, null=True, blank=True)
    tema = models.CharField(max_length=200, blank=True)
    observacoes = models.TextField("observações", blank=True)
    responsavel = models.CharField("responsável (equipe)", max_length=60, blank=True,
                                   help_text="Iniciais de quem conduziu (ex.: VH).")
    area = models.CharField("área", max_length=150, blank=True)
    orientacao = models.TextField("orientação / próximos passos", blank=True)
    encaminhamentos = models.CharField(max_length=300, blank=True,
                                       help_text="Programas para onde a pessoa foi encaminhada (WF, Spark...).")
    origem_registro = models.CharField("origem do registro", max_length=250, blank=True)
    codigo_importacao = models.CharField("código na base consolidada", max_length=12, blank=True, db_index=True)

    class Meta:
        ordering = ["-data"]
        verbose_name = "Mentoria (sessão)"
        verbose_name_plural = "Mentorias (sessões)"

    def __str__(self):
        quando = f"{self.data:%d/%m/%Y}" if self.data else "sem data"
        quem = self.mentor.nome if self.mentor_id else (self.responsavel or "equipe FACE")
        return f"Mentoria com {quem} em {quando}"


class Entrega(TimeStampedModel):
    """
    Um checkpoint/entrega esperado de um participante dentro de uma Edição
    (ex.: vídeo pitch 1, vídeo pitch 2, TCC final, pitch deck, MVP demo).
    Genérico o suficiente pra ser reaproveitado por outros programas além
    do TCC Connect.
    """

    TIPO_CHOICES = [
        ("video", "Vídeo"),
        ("documento", "Documento"),
        ("apresentacao", "Apresentação"),
        ("outro", "Outro"),
    ]

    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("entregue", "Entregue"),
        ("atrasado", "Atrasado"),
        ("dispensado", "Dispensado"),
    ]

    participacao = models.ForeignKey(Participacao, on_delete=models.CASCADE, related_name="entregas")
    projeto = models.ForeignKey(
        Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="entregas",
    )
    nome = models.CharField(max_length=150, help_text='Ex.: "Vídeo Pitch 1", "TCC Final"')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="outro")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="entregue")
    link = models.URLField(blank=True, help_text="Link do vídeo/documento, se houver.")
    data_prevista = models.DateField(null=True, blank=True)
    data_entrega = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-data_entrega"]
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"

    def __str__(self):
        return f"{self.nome} - {self.participacao.pessoa.nome}"


class Evento(TimeStampedModel):
    """Visitas técnicas, palestras, workshops, feiras etc."""

    TIPO_CHOICES = [
        ("viagem", "Viagem / missão"),
        ("visita_tecnica", "Visita técnica"),
        ("palestra", "Palestra"),
        ("workshop", "Workshop/Oficina"),
        ("feira", "Feira/Demoday"),
        ("outro", "Outro"),
    ]

    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data = models.DateField(null=True, help_text="Data do evento/viagem.")
    local = models.CharField(max_length=200, blank=True)
    descricao = models.TextField("descrição", blank=True, help_text="Texto exibido na vitrine pública.")
    vagas = models.PositiveIntegerField(null=True, blank=True)
    inscricoes_inicio = models.DateField("início das inscrições", null=True, blank=True)
    inscricoes_fim = models.DateField("fim das inscrições", null=True, blank=True)
    publicado = models.BooleanField("publicado na vitrine", default=False)
    ponto_encontro = models.CharField("ponto de encontro / embarque", max_length=200, blank=True)
    observacoes = models.TextField("observações", blank=True)
    parceiro = models.ForeignKey(
        Parceiro, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos",
    )
    edicao = models.ForeignKey(
        Edicao, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos",
    )
    participantes = models.ManyToManyField(
        Pessoa, blank=True, related_name="eventos", through="EventoParticipante",
    )

    class Meta:
        ordering = ["-data"]
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    def __str__(self):
        return f"{self.nome} ({self.data:%d/%m/%Y})" if self.data else self.nome

    @property
    def inscricoes_abertas(self):
        hoje = date.today()
        return bool(self.inscricoes_inicio and self.inscricoes_fim
                    and self.inscricoes_inicio <= hoje <= self.inscricoes_fim)


class EventoParticipante(TimeStampedModel):
    """
    Inscrição de uma Pessoa num Evento, com controle de presença separado
    da inscrição — útil pra medir taxa de comparecimento real por evento.
    """

    STATUS_CHOICES = [
        ("inscrito", "Inscrito(a)"),
        ("lista_espera", "Lista de espera"),
        ("confirmado", "Confirmado(a)"),
        ("cancelado", "Cancelou"),
    ]

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="inscricoes")
    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="inscricoes_eventos")
    status = models.CharField("situação da inscrição", max_length=15, choices=STATUS_CHOICES, default="inscrito")
    presente = models.BooleanField(
        null=True, blank=True,
        help_text="Deixe em branco até confirmar. True = compareceu, False = não compareceu.",
    )
    data_inscricao = models.DateField(null=True, blank=True)
    vinculo_na_inscricao = models.CharField(max_length=25, choices=Pessoa.TIPO_CHOICES, blank=True)
    curso_na_inscricao = models.ForeignKey(Curso, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="+")
    detalhes = models.TextField(blank=True)
    origem = models.CharField(max_length=250, blank=True, help_text="Planilha/linha de onde veio o registro.")

    class Meta:
        unique_together = ("evento", "pessoa")
        verbose_name = "Inscrição em evento"
        verbose_name_plural = "Inscrições em eventos"

    def __str__(self):
        return f"{self.pessoa.nome} - {self.evento.nome}"
