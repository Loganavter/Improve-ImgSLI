## Visão Geral do Multi Compare

Compare várias imagens em uma única sessão usando uma grade de layout, soltura por slot e modo de foco.

### Abrir uma sessão {#open-session}

Escolha {{tr:workspace.session_types.multi_compare}} no Seletor de Sessão, ou execute {{tr:action.workspace.new_multi_compare}} em {{tr:menu.find_action}} (`Ctrl+Shift+P`). Veja também [Abas do Workspace](help://session_picker).

### Layouts e divisões por lacuna {#layouts}

- **Grade** — organize os slots; solte arquivos em uma célula ou use {{tr:multi_compare.action.add_images}} (`Ctrl+O`).
- **Slots vazios** — permanecem abertos para novas solturas.
- **Soltura na lacuna** — solte em uma lacuna entre células para dividir e criar uma nova célula recursivamente.
- **Pesos** — arraste os divisores da grade para alterar os tamanhos relativos.
- **Mudança de layout** — mantém as imagens carregadas sempre que possível.

:::figure{side=center width=320}
![Grade do Multi Compare](ui/placeholder.png)
{{tr:workspace.session_types.multi_compare}} — grade / soltura na lacuna (placeholder).
:::

### Modo de foco {#focus-mode}

- **Entrar** — clique duplo em um slot para foco em tela cheia.
- **Sair** — `Esc` retorna à grade.
- **Navegar** — zoom e panorâmica como em {{tr:workspace.session_types.image_compare}}; veja [Navegação no Canvas](help://view_navigation).

### Grade e rótulos {#grid-and-labels}

- **Visibilidade** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Cor / largura** — {{tr:multi_compare.action.divider_color}} e {{tr:multi_compare.action.divider_width}}.
- **Texto do rótulo** — {{tr:multi_compare.action.text_settings}} abre a estilização (sem os botões de posicionamento do {{tr:workspace.session_types.image_compare}}).

### Menu de contexto do slot {#context-menu}

Clique com o botão direito em um slot para ações por imagem, incluindo [Propriedades da Imagem](help://image_properties) (metadados do arquivo e posição do slot).

### Salvar e exportar {#save-and-export}

- **Salvamento rápido** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}}.
- **Diálogo de salvar** (`Ctrl+Shift+S`) — {{tr:multi_compare.action.save}}.
- **Paridade** — a exportação corresponde à grade ao vivo (layout, rótulos, elementos do divisor), não a uma única divisão de {{tr:workspace.session_types.image_compare}}.

Busque salvar / exportar em {{tr:menu.find_action}} enquanto a aba {{tr:workspace.session_types.multi_compare}} estiver em foco.
