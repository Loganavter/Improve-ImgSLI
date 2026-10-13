## Layouts e slots

Os slots ficam em uma grade dividida onde você pode soltar arquivos, dividir células em uma lacuna e arrastar os divisores para redimensioná-las.

### Células e zonas de soltar {#layouts}

- **Soltura de arquivos** — solte um arquivo sobre a grade; o novo slot abre ao lado da célula sob o cursor e a divide, e a primeira soltura em uma grade vazia se torna o primeiro slot.
- **Adicionar imagens** (`Ctrl+O`) — carrega uma ou mais imagens na grade.
- **Zonas de soltar** — uma soltura de arquivo tem como alvo a célula sob o cursor e a mais próxima de suas quatro bordas.
- **Solturas externas** — arquivos soltos do gerenciador de arquivos, colados da área de transferência ou movidos com **Mover** de outra aba são posicionados automaticamente enquanto uma mensagem de progresso é exibida.
- **Posicionamento automático** — uma nova imagem divide a maior célula ao longo de seu lado mais longo, e a grade comporta no máximo 12 imagens.
- **Soltura na lacuna** — uma soltura em uma lacuna de divisor divide uma nova célula entre os dois slots vizinhos.
- **Mudança de layout** — mudar o layout mantém as imagens carregadas e apenas as reorganiza.

### Zonas de divisão na lacuna {#gap-split-zones}

Quando você solta uma imagem em uma lacuna entre dois slots, o ponto dentro da lacuna decide para onde a nova célula vai.

- **Lacuna do divisor vertical** — soltar no quarto superior da lacuna posiciona a imagem acima da linha, no quarto inferior a posiciona abaixo, e na metade do meio a posiciona entre os dois slots vizinhos.
- **Lacuna do divisor horizontal** — soltar no quarto esquerdo posiciona a imagem à esquerda da coluna, no quarto direito à direita, e na metade do meio a posiciona entre os dois slots vizinhos.

### Divisores {#dividers}

- **Arrastar** — arraste um divisor para alterar o tamanho relativo das células de cada lado.
- **Redefinir** — clique duas vezes em um divisor para igualar as células de cada lado.
- **Visibilidade da grade** (`D`) — mostra ou oculta as linhas do divisor.
- **Cor da grade** e **Linhas da grade** — definem a cor e a largura das linhas do divisor.

### Ações do slot {#context-menu}

Clique com o botão direito em um slot para ações por imagem:

- **Renomear** — edita o nome exibido no rótulo do slot.
- **Duplicar** — copia o slot; precisa de uma imagem carregada e de um slot livre.
- **Propriedades** — abre [Propriedades da imagem](help://platform.image_properties) com os metadados do arquivo e a posição do slot na grade.
- **Mover** — arrasta a imagem para outra aba, onde ela é carregada e posicionada automaticamente.
- **Recortar** — ativa ou desativa o recorte deste slot; veja [Visualização e foco](help://workspace.multi_compare.viewing#slot-crop).
- **Remover** — remove o slot e sua imagem da grade.
- **Limite de slots** — você pode carregar no máximo 12 imagens em uma grade.
