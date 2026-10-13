## Arquivos e Projetos

Carregue imagens nas listas da sessão, cole a partir da área de transferência e abra ou salve arquivos de projeto portáteis, que reúnem o layout das sessões, as configurações de comparação e cópias das imagens de origem.

### Carregando imagens {#loading-images}

- **Adicionar arquivos** — os botões de adicionar ao lado de cada lista abrem o seletor de arquivos; o mesmo comando está em **Localizar ação** (`Ctrl+Shift+P`).
- **Arrastar e soltar** — arraste os arquivos para a janela; eles entram na lista do lado sob o cursor.
- **Colar** (`Ctrl+V`) — cole uma imagem da área de transferência. Surge uma sobreposição de direção: clique em uma seta para escolher a lista, ou pressione `Esc` para cancelar.

:::figure{side=block width=280}
![Sobreposição de direção ao colar](../../assets/platform/paste_overlay.jpg)
Depois de `Ctrl+V`, a sobreposição de direção mostra o destino da imagem: cada seta aponta para uma das listas, e `Esc` cancela a colagem.
:::

### Listas {#lists}

- Em uma sessão **Comparar imagens**, as listas da esquerda e da direita são independentes. O gerenciador de lista permite reordenar, avaliar, renomear, ver o caminho, abrir **Propriedades** e remover imagens — veja [Comparação](help://workspace.image_compare.comparison).
- Em uma sessão **Comparação múltipla**, cada imagem é solta em um slot próprio em vez de duas listas — veja [Visão Geral do Multi Compare](help://workspace.multi_compare.overview).

### Projetos {#projects}

Um projeto é um único arquivo portátil `.imgsli`: ele guarda as sessões abertas, as configurações de comparação e cópias das imagens de origem.

- **Abrir um projeto** — use `Ctrl+Shift+O`, o menu **Arquivo** ou **Localizar ação**. Ao abrir, a aba ativa recebe o nome do arquivo, e o projeto restaura as sessões do workspace, as configurações de comparação (**Divisor**, modos de diferença, **Lupa** e recursos relacionados) e as cópias incorporadas das imagens.
- **Salvar** — `Shift+S` grava o arquivo atual. Se o projeto ainda não foi salvo, abre **Salvar como**. Quando a aba foi renomeada, o salvamento também atualiza o nome do arquivo.
- **Salvar como** — `Ctrl+Shift+S` sugere o título da aba renomeada; caso contrário, usa **Sem título**.
- **O que o arquivo contém** — o projeto é um ZIP: o JSON das sessões e uma pasta `media/` com cópias dos originais, sem recodificar os pixels.
- **Se um original sumiu** — quando um caminho da lista não existe mais, o projeto ainda é salvo; essa imagem é omitida e um aviso informa qual ficou de fora.
- **O que não é salvo** — **Tema**, **Idioma** e atalhos ficam nas configurações do aplicativo e não fazem parte do arquivo de projeto.
