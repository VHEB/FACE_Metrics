"""
Catálogo: quais planilhas existem, como cada uma é lida e a que atividade pertence.

Para incluir uma planilha nova (ex.: a próxima edição de uma viagem), acrescente
uma atividade em ATIVIDADES e uma linha em FONTES. O arquivo é encontrado pelo
nome (ignorando acentos, espaços e pontuação), então pode ficar em qualquer pasta.

Campos de uma atividade:
    tipo, programa, edicao, nome   identificação
    data_evento, local             viagens e eventos
    cores      {cor: status}       o que a equipe quer dizer ao pintar a linha na planilha
    sem_cor    status de quem NÃO está pintado (só quando a cor marca a exceção, ex.: faltas)
    nota       informação que aparece na tabela de atividades
    confirmar  dúvida que vai para a planilha de revisão
Status usados: inscrito, presente, ausente, participou, não participou, concluiu, desistiu, lista de espera.
"""

# cores confirmadas pela equipe na revisão de 12/11/2026
_TCC_CORES = {"verde": "concluiu", "vermelho": "desistiu"}
_FALTAS = {"vermelho": "ausente", "vermelho claro": "ausente", "amarelo": "ausente"}

ATIVIDADES = {
    # ---- programas
    "tcc-connect-2025-1": dict(tipo="programa", programa="TCC Connect", edicao="2025.1", cores=_TCC_CORES,
                               nota="Inscrições no fim do semestre anterior (dez/2024 a mar/2025) para iniciar em "
                                    "2025.1. O arquivo se chama '2025S2'."),
    "tcc-connect-2025-2": dict(tipo="programa", programa="TCC Connect", edicao="2025.2", cores=_TCC_CORES),
    "tcc-connect-2026-1": dict(tipo="programa", programa="TCC Connect", edicao="2026.1", cores=_TCC_CORES),
    "internacionalizacao-2025": dict(tipo="programa", programa="Internacionalização de Startups", edicao="2025",
                                     cores={"verde": "participou", "vermelho": "não participou"}),
    "piemp-2026": dict(tipo="programa", programa="PIEMP", edicao="2026"),
    "wadhwani-espera-2024": dict(tipo="programa", programa="Ideação Wadhwani (WF)", edicao="2024 — lista de espera"),
    # ---- viagens
    "case-2022": dict(tipo="viagem", programa="CASE", edicao="2022", nome="CASE 2022 (transporte)",
                      data_evento="2022-11-17", local="Transamerica Expo Center, São Paulo, SP",
                      nota="O arquivo se chama 'CASE 2023'; inscrições de fev a mai/2022."),
    "innovation-week-2024": dict(tipo="viagem", programa="Innovation Week", edicao="2024",
                                 nome="Innovation Week 2024 (transporte)", data_evento="2024-06-12",
                                 local="Prédio do Relógio (Pátio Ferroviário), Campinas, SP"),
    "innovation-week-2025": dict(tipo="viagem", programa="Innovation Week", edicao="2025",
                                 nome="Innovation Week 2025 (transporte)", data_evento="2025-06-11",
                                 local="Prédio do Relógio (Pátio Ferroviário), Campinas, SP"),
    "scibiz-9": dict(tipo="viagem", programa="SciBiz", edicao="9ª edição (2026)", nome="SciBiz — 9ª edição",
                     data_evento="2026-05-12", local="São Paulo, SP"),
    "beauty-fair-2026": dict(tipo="viagem", programa="Beauty Fair", edicao="2026", nome="Beauty Fair 2026",
                             data_evento="2026-09-08", local="Expo Center Norte, São Paulo, SP"),
    "innovation-week-campinas-2026": dict(tipo="viagem", programa="Innovation Week Campinas", edicao="2026",
                                          nome="Innovation Week Campinas 2026", data_evento="2026-09-15",
                                          local="Prédio do Relógio (Pátio Ferroviário), Campinas, SP"),
    "feira-empreendedor-2026": dict(tipo="viagem", programa="Feira do Empreendedor", edicao="2026",
                                    nome="Feira do Empreendedor 2026", data_evento="2026-10-21",
                                    local="São Paulo Expo, São Paulo, SP",
                                    cores=_FALTAS, sem_cor="presente",
                                    nota="Amarelo = não respondeu se iria (considerado falta)."),
    # ---- eventos
    "palestra-habilidades-2026": dict(tipo="evento", programa="Palestras", edicao="2026",
                                      nome="Palestra: Habilidades Essenciais para Empreender",
                                      local="UniFacens, Sorocaba, SP", cores=_FALTAS, sem_cor="presente"),
}

# (regex sobre o nome do arquivo compactado, leitor, parâmetros)
FONTES = [
    # Programa de Mentorias
    (r"agendamentomentorias.*2023", "pedidos", dict(ano=2023, origem="Programa de Mentorias")),
    (r"agendamentomentorias.*2024", "pedidos", dict(ano=2024, aba="SOLICITAÇÕES", origem="Programa de Mentorias")),
    (r"agendamentomentorias.*2024", "sessoes", dict(aba="REALIZADAS - FACE")),
    (r"agendamentomentorias.*2024", "sessoes_voluntarios", dict(aba="REALIZADAS - mentores")),
    (r"agendamentomentorias.*2024", "lista_espera", dict(aba="LISTA DE ESPERA", atividade="wadhwani-espera-2024")),
    (r"agendamentomentorias.*2025", "pedidos", dict(ano=2025, aba="Respostas", origem="Programa de Mentorias")),
    (r"agendamentomentorias.*2025", "sessoes", dict(aba="Realizadas")),
    (r"agendamentomentorias.*2026", "pedidos", dict(ano=2026, aba="Respostas", origem="Programa de Mentorias")),
    (r"agendamentomentorias.*2026", "sessoes", dict(aba="Realizadas")),
    # Extensão (mentorias das turmas de extensão: ADS/GTI Projeto Startup, Gestão da Inovação...)
    (r"extens.*2025s1", "pedidos", dict(ano=2025, origem="Extensão", vinculo_padrao="aluno")),
    (r"extens.*2025s2", "pedidos", dict(ano=2025, origem="Extensão", vinculo_padrao="aluno")),
    (r"extens.*2026", "pedidos", dict(ano=2026, aba="Respostas", origem="Extensão", vinculo_padrao="aluno")),
    (r"extens.*2026", "sessoes", dict(aba="Página1")),
    # Programas
    (r"tccconnect2025s2", "tcc_connect", dict(atividade="tcc-connect-2025-1")),
    (r"tccconnect20252\w?semestre", "tcc_connect", dict(atividade="tcc-connect-2025-2")),
    (r"tccconnect2026", "tcc_connect", dict(atividade="tcc-connect-2026-1")),
    (r"programadeinternacionaliza", "internacionalizacao", dict(atividade="internacionalizacao-2025")),
    (r"piemp2026", "piemp", dict(atividade="piemp-2026")),
    # Viagens
    (r"transportecase", "inscricoes", dict(atividade="case-2022", vinculo_padrao="aluno")),
    (r"transporteinnovationweek2024", "inscricoes", dict(atividade="innovation-week-2024")),
    (r"transporteinnovationweek2025", "inscricoes", dict(atividade="innovation-week-2025")),
    (r"scibiz", "inscricoes", dict(atividade="scibiz-9")),
    (r"beautyfair", "inscricoes", dict(atividade="beauty-fair-2026")),
    (r"innovationweekcampinas", "inscricoes", dict(atividade="innovation-week-campinas-2026")),
    (r"feiradoempreendedor", "inscricoes", dict(atividade="feira-empreendedor-2026")),
    # Eventos
    (r"palestra.*habilidades", "inscricoes", dict(atividade="palestra-habilidades-2026")),
]
