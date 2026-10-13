## Configurações

Comportamento do aplicativo em um diálogo: páginas nativas mais seções das abas do workspace (análise do comparador, credenciais de IA da galeria). Seções de abas ficam visíveis seja qual for a sessão ativa.

### Abrir Configurações {#open-settings}

- **Menu** — {{tr:menu.settings}} (`Ctrl+,`).
- **Barra de ferramentas** — o botão de engrenagem.
- **Find Action** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) e o nome da página ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — numa ação de configuração abre a âncora correspondente quando marcada.

### Pesquisar nas Configurações {#search}

Um campo de pesquisa sobre a lista: resultados vêm uma linha por seção, não importa a profundidade do acerto (nome de controle, título de grupo, qualquer idioma). Ativar a linha abre a seção com as opções pulsando. `Esc` limpa a pesquisa e restaura a lista. A lista é redimensionável.

### Geral {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — chave de notificações do SO.
- **{{tr:settings.enable_debug_logging}}** — logs detalhados para depuração.

### Aparência {#interface}

- **{{tr:settings.ui_mode}}** — botões {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}; o padrão é iniciante, e a escolha da primeira abertura cai aqui.
- **{{tr:settings.ui_font}}** — fonte nativa, padrão do sistema ou personalizada.
- **{{tr:settings.ui_scale}}** — escala da interface (0,5–2,5).
- **Limites** — tetos afins, como o comprimento máximo do nome exibido.

### Desempenho {#performance}

- **{{tr:settings.render_backend_label}}** — os backends oferecidos dependem da plataforma; trocar pode exigir reiniciar.

### {{tr:workspace.session_types.image_compare}} {#image_compare}

Opções do comparador, sempre disponíveis:

- **Interpolação** — qualidade de reamostragem de zoom / lupa / laser.
- **{{tr:settings.optimize_magnifier_movement}}** — movimento mais suave da lente, com o método de interpolação na mesma linha.
- **{{tr:settings.magnifier_intersection_highlight}}** — destaque onde as lentes se cruzam.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — cores distintas para novas lentes.
- **{{tr:image_compare.settings.recording_fps}}** — taxa de captura para o [Editor de vídeo](help://workspace.image_compare.video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — corta bordas pretas ao carregar.
- **Auto {{tr:ui.psnr}} / {{tr:ui.ssim}}** — leitura automática de métricas, desligada por padrão.

### Teclado {#keyboard}

- **Remapear** — atalhos por dono: platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Redefinir** — um atalho ou todos.
- **Fixos** — `WASD` e `Space` no canvas ficam fixos — ver [Atalhos](help://platform.hotkeys).
