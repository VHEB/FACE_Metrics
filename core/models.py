"""
Modelos do FACE Metrics.

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

from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator


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

    class Meta:
        ordering = ["-ano", "-semestre"]
        unique_together = ("programa", "ano", "semestre")
        verbose_name = "Edição"
        verbose_name_plural = "Edições"

    def __str__(self):
        periodo = f"{self.ano}.{self.semestre}" if self.semestre else str(self.ano)
        return f"{self.programa.nome} - {periodo}"


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

    cpf_validator = RegexValidator(
        regex=r"^\d{11}$",
        message="CPF deve conter 11 dígitos numéricos (sem pontuação).",
    )

    nome = models.CharField(max_length=200)
    cpf = models.CharField(
        max_length=11, validators=[cpf_validator],
        blank=True, null=True, unique=True,
        help_text="Somente números. Campo sensível — tratar com cuidado (LGPD).",
    )
    rg = models.CharField(max_length=20, blank=True, help_text="Campo sensível — tratar com cuidado (LGPD).")
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    tipo_pessoa = models.CharField(max_length=25, choices=TIPO_CHOICES)

    curso = models.ForeignKey(
        Curso, on_delete=models.SET_NULL, null=True, blank=True, related_name="pessoas",
        help_text="Preencher apenas se aluno(a) ou ex-aluno(a).",
    )
    ra = models.CharField("RA", max_length=20, blank=True)
    semestre_ingresso = models.CharField(max_length=10, blank=True, help_text="Ex.: 2023.1")

    cidade = models.CharField(max_length=100, blank=True)

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
        ("mentor", "Mentor(a)"),
        ("mentorado", "Mentorado(a)"),
        ("organizador", "Organizador(a)"),
        ("palestrante", "Palestrante"),
    ]

    STATUS_CHOICES = [
        ("inscrito", "Inscrito(a)"),
        ("em_andamento", "Em andamento"),
        ("concluido", "Concluído"),
        ("desistente", "Desistente"),
    ]

    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="participacoes")
    edicao = models.ForeignKey(Edicao, on_delete=models.CASCADE, related_name="participacoes")
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES, default="participante")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inscrito")
    data_entrada = models.DateField(null=True, blank=True)
    data_saida = models.DateField(null=True, blank=True)

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

class Mentoria(TimeStampedModel):
    """Registro de uma sessão de mentoria."""

    TIPO_CHOICES = [
        ("diagnostico", "Diagnóstico (triagem inicial)"),
        ("acompanhamento", "Acompanhamento"),
        ("outro", "Outro"),
    ]

    mentor = models.ForeignKey(
        Pessoa, on_delete=models.PROTECT, related_name="mentorias_realizadas",
        limit_choices_to={"tipo_pessoa__in": ["mentor_parceiro", "docente", "colaborador"]},
    )
    mentorados = models.ManyToManyField(Pessoa, related_name="mentorias_recebidas")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="acompanhamento")
    edicao = models.ForeignKey(
        Edicao, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentorias",
    )
    projeto = models.ForeignKey(
        Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentorias",
    )
    data = models.DateField()
    duracao_minutos = models.PositiveIntegerField(default=60)
    tema = models.CharField(max_length=200, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-data"]
        verbose_name = "Mentoria"
        verbose_name_plural = "Mentorias"

    def __str__(self):
        return f"Mentoria de {self.mentor.nome} em {self.data:%d/%m/%Y}"


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
        ("visita_tecnica", "Visita técnica"),
        ("palestra", "Palestra"),
        ("workshop", "Workshop/Oficina"),
        ("feira", "Feira/Demoday"),
        ("outro", "Outro"),
    ]

    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data = models.DateField()
    local = models.CharField(max_length=200, blank=True)
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
        return f"{self.nome} ({self.data:%d/%m/%Y})"


class EventoParticipante(TimeStampedModel):
    """
    Inscrição de uma Pessoa num Evento, com controle de presença separado
    da inscrição — útil pra medir taxa de comparecimento real por evento.
    """

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="inscricoes")
    pessoa = models.ForeignKey(Pessoa, on_delete=models.CASCADE, related_name="inscricoes_eventos")
    presente = models.BooleanField(
        null=True, blank=True,
        help_text="Deixe em branco até confirmar. True = compareceu, False = não compareceu.",
    )

    class Meta:
        unique_together = ("evento", "pessoa")
        verbose_name = "Inscrição em evento"
        verbose_name_plural = "Inscrições em eventos"

    def __str__(self):
        return f"{self.pessoa.nome} - {self.evento.nome}"
