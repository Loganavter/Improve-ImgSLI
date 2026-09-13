## Configurações

As configurações são agrupadas por tarefa — geral, aparência, desempenho e teclado — mais uma seção por aba de workspace que contribui com configurações ({{tr:workspace.session_types.image_compare}}, …). As seções das abas ficam sempre visíveis, independentemente da sessão ativa, então as opções da aba têm um lugar permanente.

### Abrir Configurações {#open-settings}

- **Menu / engrenagem** — {{tr:menu.settings}} ou a engrenagem na barra de ferramentas.
- **Localizar Ação** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) e digite o nome de uma página ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — em uma ação de configurações leva direto aqui, com a âncora correspondente quando marcada.

### Pesquisar nas Configurações {#search}

Um campo de busca fica acima da barra lateral: digite qualquer coisa e as seções correspondentes são listadas — uma linha por seção, não importa quão profunda seja a correspondência (nome de controle, título de grupo, qualquer idioma). Ative uma linha para abrir essa seção: as opções correspondentes dentro dela se destacam (se várias coincidirem no mesmo nível, todas elas). A busca funciona em todos os idiomas da interface, como {{tr:menu.find_action}}. `Esc` limpa a busca e restaura a barra lateral completa. A barra lateral em si é redimensionável — arraste o divisor entre ela e o conteúdo das configurações.

### Geral {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — automático / claro / escuro.
- **{{tr:settings.system_notifications}}** — notificações do sistema operacional após salvar (o toast no app é separado).
- **{{tr:settings.enable_debug_logging}}** — logs detalhados para depuração.

### Aparência {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}.
- **{{tr:settings.ui_font}}** — família embutida, do sistema, ou personalizada.
- **{{tr:settings.ui_scale}}** — escala da interface independente da escala de exibição do sistema (0.5–2.5); aplica ao vivo — controles, fontes, ícones e espaçamento são redimensionados imediatamente.
- **Limites** — limites relacionados, como o comprimento máximo do nome exibido.

### Desempenho {#performance}

- **{{tr:settings.render_backend_label}}** — depende da plataforma; pode exigir reinicialização.

### {{tr:workspace.session_types.image_compare}} {#image_compare}

As opções específicas de comparação de imagens ficam em sua própria seção, sempre disponível:

- **{{tr:settings.display_cache_resolution}}** — limita o tamanho da pré-visualização principal; a lupa e a exportação continuam usando os originais.
- **Interpolação** — qualidade de reamostragem do zoom / lupa / laser.
- **{{tr:settings.optimize_magnifier_movement}}** — movimento mais suave da lente (e seu método de interpolação, na mesma página).
- **{{tr:settings.magnifier_intersection_highlight}}** — destaca onde as lentes se sobrepõem.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — cores distintas para novas lentes.
- **{{tr:settings.recording_fps}}** — taxa de captura para o [Editor de Vídeo](help://video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — corta bordas pretas ao carregar.
- **{{tr:ui.psnr}} / {{tr:ui.ssim}} automáticos** — abaixo do canvas (desativado por padrão).

### Teclado {#keyboard}

- **Remapear** — busque ações; combinações por grupo de plataforma / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Redefinir** — um atalho ou todos.
- **Fixos** — `WASD` e `Space` do canvas permanecem fixos — veja [Atalhos de Teclado](help://hotkeys).
