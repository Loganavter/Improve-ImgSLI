## Atalhos de Teclado

Combinações padrão abaixo. A maioria dos atalhos de ação aceita remapeamento em {{tr:menu.settings}} → {{tr:settings.keyboard}}. Os movimentos `WASD`, setas, `Space` e o zoom `+`/`-` do canvas permanecem fixos e não podem ser remapeados.

### Descubra primeiro {#discover}

`Ctrl+Shift+P` mais um nome digitado vence a memorização de listas: a paleta executa a ação ou abre {{tr:action.palette.learn_more}} com o tópico ilustrado. F1 destaca a ação correspondente quando o foco está marcado.

### Plataforma {#platform}

- `Ctrl+,` — Configurações
- `Ctrl+F1` — Ajuda
- `Ctrl+N` — Seletor de sessão / nova sessão
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — Próxima / sessão anterior do workspace
- `Ctrl+Shift+P` — {{tr:menu.find_action}}
- `Ctrl+V` — Colar imagem
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — Abrir / salvar / salvar projeto como (`.imgsli`)
- `Ctrl+Q` — Sair

Os rótulos exatos seguem o pacote de idioma; as substituições ficam em Configurações → Teclado → grupo de plataforma.

### {{tr:workspace.session_types.image_compare}} {#image-compare}

- `M` / `F` — Lupa / congelar
- `N` / `D` — Rótulos de nome de arquivo / visibilidade do divisor
- `H` / `C` — Modo de diferença / modo de canal
- `X` — Trocar
- `R` / `Ctrl+E` — Gravar / Editor de Vídeo
- `Ctrl+S` — Salvamento rápido
- `WASD` / `QE` — Mover lupa / espaçamento (fixos)
- `Shift` + `Space` — Pré-visualização de lado no modo combinado (fixo)
- `←↑↓→` / `+` / `-` — Panorâmica / zoom (fixos)

Detalhes: [Comparação](help://comparison), [Lupa](help://magnifier), [Editor de Vídeo](help://video).

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

- `Ctrl+O` — Adicionar imagens
- `D` — Visibilidade da grade
- `Ctrl+S` — Salvamento rápido
- `Esc` — Sair do foco do slot
- `←↑↓→` / `+` / `-` — Panorâmica / zoom (fixos)

Veja [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).

### Janela do editor de vídeo {#video-editor}

Enquanto o editor está aberto: `Space` reproduz/pausa, `Ctrl+Z` / `Ctrl+Y` desfazer/refazer, `Delete` / `Backspace` apara para a seleção. Fluxo completo de codificação: [Editor de Vídeo](help://video).

### Navegação pelo teclado {#keyboard-navigation}

- `F1` — ajuda contextual para o controle em foco. Quando o foco está vinculado a uma ação, o resultado correspondente pulsa em {{tr:menu.find_action}}; caso contrário, a paleta abre pré-filtrada por tópico.
- Em {{tr:menu.find_action}} (`Ctrl+Shift+P`): `↑` / `↓` movem a seleção, `Enter` executa, `Ctrl+Enter` abre {{tr:action.palette.learn_more}}, `Esc` fecha a paleta.
- Na visão geral de {{tr:workspace.session_types.multi_compare}}, o foco do slot segue o ponteiro: um clique alterna o foco em uma única imagem, `Esc` sai dele. As setas deslocam o canvas em vez de mover o foco entre slots.
- No seletor de sessão, as setas movem o foco entre cartões e `Enter` abre o cartão em foco, como clicar nele.
- Não há travessia `Tab` entre slots do canvas: o foco segue o ponteiro, e o teclado aciona ações pela paleta.
