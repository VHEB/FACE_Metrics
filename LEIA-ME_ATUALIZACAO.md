# Atualização FACE Metrics — modelos novos e carga das planilhas (12/11/2026)

## Antes de começar
Faça um commit (ou cópia da pasta) do projeto como está. Assim dá para voltar se algo der errado.

## Passo a passo (na pasta do projeto, com o .venv ativado)

1. **Copie o conteúdo deste zip por cima do projeto**, mantendo as pastas (core\, portal\, dashboard\...).
   Aceite substituir os arquivos.

2. **Apague os importadores antigos** (foram substituídos pela consolidação):
   ```
   core\management\commands\importar_mentorias.py
   core\management\commands\importar_tcc_connect.py
   core\management\commands\importar_transporte.py
   core\management\commands\_importer_utils.py
   ```

3. **Atualize o banco e o catálogo de programas:**
   ```powershell
   python manage.py migrate
   python manage.py seed_programas
   ```

4. **Simule a carga** (não altera nada):
   ```powershell
   python -X utf8 manage.py carregar_base_consolidada dados\saida\base_consolidada_face.json
   ```

5. **Carregue de verdade:**
   ```powershell
   python -X utf8 manage.py carregar_base_consolidada dados\saida\base_consolidada_face.json --confirmar
   ```
   Antes de apagar qualquer coisa, o comando salva um backup em `backups\` e mostra no fim o comando para desfazer.

6. **Confira:**
   ```powershell
   python manage.py test core
   python manage.py runserver
   ```
   Abra http://localhost:8000/portal/pedidos/ e http://localhost:8000/dashboard/

## Quando reconsolidar as planilhas
Rode o `consolidar.py` e repita os passos 4 e 5. A carga substitui os dados pelo conteúdo da base consolidada.

Atenção: enquanto as planilhas forem a fonte oficial, alterações feitas direto no sistema (status de pedido,
sessões registradas pelo portal) são substituídas na próxima carga. O backup guarda o estado anterior.
