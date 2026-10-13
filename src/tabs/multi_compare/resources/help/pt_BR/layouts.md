## Layouts da Comparação múltipla

A grade dá a cada imagem seu próprio **slot**, e os **divisores** entre os slots definem quanto espaço cada um ocupa.

### Células e zonas de soltar {#layouts}

- **Adicionar imagens** (`Ctrl+O`) — carrega uma ou mais imagens na grade.
- **Soltura de arquivos** — um arquivo solto sobre a grade abre um slot ao lado da célula sob o cursor e a divide; a primeira soltura em uma grade vazia se torna o primeiro slot. Uma soltura tem como alvo a mais próxima das quatro bordas da célula.
- **Solturas externas** — arquivos soltos do gerenciador de arquivos, colados da área de transferência, ou movidos com **Move** de outra aba são posicionados automaticamente enquanto uma mensagem de progresso é exibida.
- **Posicionamento automático** — uma imagem recém-adicionada divide a maior célula ao longo de seu lado mais longo.
- **Soltura na lacuna** — uma soltura em uma lacuna de divisor divide uma nova célula entre os dois slots vizinhos.
- **Mudança de layout** — mudar o layout mantém as imagens carregadas e apenas as reorganiza.

### Zonas de divisão na lacuna {#gap-split-zones}

Quando uma imagem é solta na lacuna entre dois slots, o ponto dentro da lacuna decide para onde a nova célula vai.

- **Lacuna do divisor vertical** — soltar no quarto superior da lacuna posiciona a imagem acima da linha, no quarto inferior a posiciona abaixo, e na metade do meio a posiciona entre os dois slots vizinhos.
- **Lacuna do divisor horizontal** — soltar no quarto esquerdo posiciona a imagem à esquerda da coluna, no quarto direito à direita, e na metade do meio a posiciona entre os dois slots vizinhos.

### Divisores {#dividers}

- **Arrastar** — arraste um divisor para alterar o tamanho relativo das células de cada lado.
- **Redefinir** — clique duas vezes em um divisor para igualar as células de cada lado.
- **Visibilidade da grade** (`D`) — mostra ou oculta as linhas dos divisores.
- **Cor da grade** e **Linhas da grade** — definem a cor e a largura das linhas dos divisores.

### Ações do slot {#context-menu}

Clique com o botão direito em um slot para ações por imagem:

- **Rename** — edita o nome exibido no rótulo do slot.
- **Duplicate** — copia o slot; precisa de uma imagem carregada.
- **Properties** — abre [Propriedades da imagem](help://platform.image_properties) com os metadados do arquivo e a posição do slot na grade.
- **Move** — entrega a imagem a outra aba, onde ela é carregada e posicionada automaticamente.
- **Crop** — ativa ou desativa o recorte deste slot; veja [Visualização da Comparação múltipla](help://workspace.multi_compare.viewing#slot-crop).
- **Remove** — remove o slot e sua imagem da grade.
