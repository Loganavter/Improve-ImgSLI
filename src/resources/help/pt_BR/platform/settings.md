## Configurações

As configurações são agrupadas por finalidade — geral, aparência, desempenho, análise e teclado — para você alterar um assunto por vez.

### Abrir Configurações {#open-settings}

- **Menu / engrenagem** — {{tr:menu.settings}} ou a engrenagem na barra de ferramentas.
- **Localizar Ação** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) e digite o nome de uma página ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — em uma ação de configurações leva direto aqui, com a âncora correspondente quando marcada.

### Geral {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — automático / claro / escuro.
- **{{tr:settings.system_notifications}}** — notificações do sistema operacional após salvar (o toast no app é separado).
- **{{tr:settings.enable_debug_logging}}** — logs detalhados para depuração.
- **{{tr:settings.show_workspace_tabs}}** — mostrar ou ocultar a faixa de abas de sessão.

### Aparência {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}.
- **{{tr:settings.ui_font}}** — família embutida, do sistema, ou personalizada.
- **Limites** — limites relacionados, como o comprimento máximo do nome exibido.

### Desempenho {#performance}

- **{{tr:settings.render_backend_label}}** — depende da plataforma; pode exigir reinicialização.
- **{{tr:settings.display_cache_resolution}}** — limita o tamanho da pré-visualização principal; a lupa e a exportação continuam usando os originais ({{tr:workspace.session_types.image_compare}}).
- **Interpolação** — qualidade de reamostragem do zoom / lupa / laser.
- **{{tr:settings.optimize_magnifier_movement}}** — movimento mais suave da lente (e seu método de interpolação, na mesma página).
- **{{tr:settings.magnifier_intersection_highlight}}** — destaca onde as lentes se sobrepõem.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — cores distintas para novas lentes.
- **{{tr:settings.recording_fps}}** — taxa de captura para o [Editor de Vídeo](help://video).

### Análise {#analysis}

Somente para {{tr:workspace.session_types.image_compare}}:

- **{{tr:settings.autocrop_black_borders_on_load}}** — corta bordas pretas ao carregar.
- **{{tr:ui.psnr}} / {{tr:ui.ssim}} automáticos** — abaixo do canvas (desativado por padrão).

Abra essa página com uma sessão {{tr:workspace.session_types.image_compare}} ativa, se a aba contribuir com essa seção.

### Teclado {#keyboard}

- **Remapear** — busque ações; combinações por grupo de plataforma / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Redefinir** — um atalho ou todos.
- **Fixos** — `WASD` e `Space` do canvas permanecem fixos — veja [Atalhos de Teclado](help://hotkeys).
