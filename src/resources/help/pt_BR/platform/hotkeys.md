## Atalhos de Teclado

A lista abaixo traz as combinações padrão. A maioria dos atalhos de ação pode ser remapeada em **Configurações** → **Teclado**. Os movimentos `WASD`, as setas, `Space` e o zoom `+`/`-` no canvas são fixos e não podem ser remapeados.

### Descubra primeiro {#discover}

**Localizar ação** (`Ctrl+Shift+P`) mais parte do nome é mais rápido do que decorar a lista: ela executa a ação ou abre **Saiba mais** com o tópico ilustrado. Se o controle em foco estiver ligado a uma ação, `F1` destaca a correspondência em **Localizar ação**.

### Plataforma {#platform}

- `Ctrl+,` — **Configurações**
- `Ctrl+F1` — **Ajuda**
- `Ctrl+N` — **Abrir seletor de sessão** / nova sessão
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — próxima / sessão anterior do workspace
- `Ctrl+Shift+P` — **Localizar ação**
- `Ctrl+V` — **Colar imagem**
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — abrir, salvar e **Salvar como** o projeto (`.imgsli`)
- `Ctrl+Q` — **Sair**

Os rótulos exatos seguem o pacote de idioma; as substituições ficam em **Configurações** → **Teclado**, no grupo de plataforma.

`Shift+S` salva o projeto em um arquivo `.imgsli`, enquanto `Ctrl+S` salva o resultado da comparação atual.

### Comparar imagens {#image-compare}

- `M` / `F` — **Alternar lupa** / **Congelar lupa**
- `N` / `D` — **Sobreposição de nomes** / **Visibilidade do divisor**
- `H` / `C` — **Modo de diferença** / **Modo de canal**
- `X` — **Trocar** as imagens
- `R` / `Ctrl+E` — **Gravar vídeo** / **Editor de vídeo**
- `Ctrl+S` — **Salvamento rápido**
- `WASD` / `QE` — mover a **Lupa** / o espaçamento entre lupas (fixos)
- `Shift+Space` — pré-visualizar um lado no modo combinado (fixo)
- `←↑↓→` / `+` / `-` — panorâmica / zoom (fixos)

Detalhes: [Comparação](help://workspace.image_compare.comparison), [Lupa](help://workspace.image_compare.magnifier), [Editor de vídeo](help://workspace.image_compare.video).

### Comparação múltipla {#multi-compare}

- `Ctrl+O` — **Adicionar imagens**
- `D` — **Visibilidade da grade**
- `Ctrl+S` — **Salvamento rápido**
- `Esc` — sair do foco do slot
- `←↑↓→` / `+` / `-` — panorâmica / zoom (fixos)

Veja [Visão Geral do Multi Compare](help://workspace.multi_compare.overview).

### Janela do editor de vídeo {#video-editor}

Enquanto a janela do editor estiver aberta:

- `Space` — reproduzir ou pausar
- `Ctrl+Z` / `Ctrl+Y` — desfazer / refazer
- `Delete` / `Backspace` — cortar até a seleção

Fluxo completo de codificação: [Editor de vídeo](help://workspace.image_compare.video).

### Navegação pelo teclado {#keyboard-navigation}

- `F1` — ajuda contextual para o controle em foco. Quando o foco está ligado a uma ação, a correspondência é destacada em **Localizar ação**; caso contrário, **Localizar ação** abre pré-filtrada por tópico.
- Em **Localizar ação** (`Ctrl+Shift+P`): `↑` / `↓` movem a seleção, `Enter` executa, `Ctrl+Enter` abre **Saiba mais**, `Esc` fecha a lista.
- Na visão geral de **Comparação múltipla**, o foco do slot segue o ponteiro: um clique alterna o foco em uma única imagem, `Esc` sai dele. As setas deslocam o canvas em vez de mover o foco entre slots.
- No **seletor de sessão**, as setas movem o foco entre cartões e `Enter` abre o cartão em foco, como clicar nele.
- Não há travessia com `Tab` entre slots do canvas: o foco segue o ponteiro, e o teclado aciona as ações pela **Localizar ação**.
