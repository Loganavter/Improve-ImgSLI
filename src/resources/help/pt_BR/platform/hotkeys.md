---
description: Consultar um atalho ou remapear os que você usa.
icon: enter.svg
---
## Atalhos de Teclado

Abaixo estão as combinações padrão. A maioria dos atalhos de ação pode ser remapeada em **Configurações** → **Teclado**; as teclas do canvas `WASD` / `QE`, as setas, `Space` e `+` / `-` são fixas e não podem ser remapeadas.

:::figure{side=block width=100%}
![Configurações de teclado](../../assets/platform/settings_keyboard.png)
**Configurações → Teclado**: cada ação da Plataforma com sua combinação e um botão **Redefinir**; abaixo vêm os grupos por aba.
:::

### Descubra primeiro {#discover}

`Ctrl+Shift+P` mais parte de um nome é mais rápido que percorrer a lista: **Localizar ação** executa a ação correspondente ou abre **Saiba mais** com o tópico ilustrado. `F1` abre o tópico de ajuda do controle em foco.

### Plataforma {#platform}

- `Ctrl+,` — **Configurações**
- `Ctrl+F1` — **Mostrar ajuda**
- `Ctrl+N` — **Nova sessão** (abre o **Seletor de Sessão**)
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — próxima / sessão anterior
- `Ctrl+Shift+P` — **Localizar ação**
- `Ctrl+V` — **Colar imagem da área de transferência**
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — **Abrir projeto** / **Salvar projeto** / **Salvar projeto como…** (`.imgsli`)
- `Ctrl+Q` — **Sair**

Os rótulos do menu seguem o idioma selecionado. Atalhos personalizados são definidos em **Configurações** → **Teclado**, no grupo da plataforma.

### Comparar imagens {#image-compare}

- `M` / `F` — **Alternar lupa** / **Congelar lupa**
- `N` / `D` — **Sobreposição de nomes** / **Visibilidade do divisor**
- `H` / `C` — **Modo de diferença** / **Modo de canal**
- `X` — **Trocar imagens**
- `R` / `Ctrl+E` — **Gravar vídeo** / **Editor de vídeo**
- `Ctrl+S` — **Salvamento rápido**
- `WASD` / `QE` — mover a lupa / ajustar seu espaçamento (fixo)
- `Shift+Space` — pré-visualizar um lado no modo combinado (fixo)
- `←↑↓→` / `+` / `-` — panorâmica / zoom (fixo)

Detalhes: [Comparação](help://workspace.image_compare.comparison), [Lupa](help://workspace.image_compare.magnifier), [Editor de vídeo](help://workspace.image_compare.video).

### Comparação múltipla {#multi-compare}

- `Ctrl+O` — **Adicionar imagens**
- `D` — **Visibilidade da grade**
- `Ctrl+S` — **Salvamento rápido**
- `Esc` — sair do foco do slot
- `←↑↓→` / `+` / `-` — panorâmica / zoom (fixo)

Veja [Visão Geral do Multi Compare](help://workspace.multi_compare.overview).

### Galeria {#image-gallery}

- `Space` / `Delete` — remover as imagens selecionadas da grade; os arquivos permanecem no disco.

Veja [Triagem e revisão](help://workspace.image_gallery.triage).

### Janela do editor de vídeo {#video-editor}

Enquanto a janela do editor estiver aberta:

- `Space` — reproduzir ou pausar
- `Ctrl+Z` / `Ctrl+Y` — desfazer / refazer
- `Delete` / `Backspace` — remover o intervalo selecionado

Fluxo completo de codificação: [Editor de vídeo](help://workspace.image_compare.video).

### Navegação pelo teclado {#keyboard-navigation}

- `F1` — abre o tópico de ajuda do controle em foco; um controle sem tópico resolvível recorre à **Localizar ação** (com a ação correspondente destacada, quando houver uma).
- Em **Localizar ação** (`Ctrl+Shift+P`): `↑` / `↓` movem a seleção, `Enter` executa, `Ctrl+Enter` abre **Saiba mais**, `Esc` fecha a lista.
- Na visão geral de **Comparação múltipla**, o foco do slot segue o ponteiro: um clique alterna o foco em uma única imagem, `Esc` sai dele. As setas movem o canvas em vez de mover o foco entre slots.
- No **Seletor de Sessão**, as setas movem o foco entre cartões e `Enter` abre o cartão em foco, como clicar nele.
- Não há travessia com `Tab` entre slots do canvas: o foco segue o ponteiro, e o teclado aciona as ações pela **Localizar ação**.
