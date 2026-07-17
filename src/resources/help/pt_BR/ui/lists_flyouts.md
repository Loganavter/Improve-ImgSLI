## Listas e Painéis

Os menus suspensos abrem painéis dentro da janela, sobre a janela principal. Trabalhe dentro do painel e depois feche com um clique fora ou `Esc`. Os gestos estão descritos em [Botões e Controles](help://ui.buttons); o estilo dos rótulos de nome de arquivo em [Comparação](help://comparison).

### Gerenciador de lista {#list-manager}

Em uma sessão {{tr:workspace.session_types.image_compare}}, cada lado tem um menu suspenso de lista. Um clique abre o painel de gerenciamento de lista daquele lado (linhas, avaliações, arraste). O painel permanece fechado se a lista estiver vazia. Clique no mesmo menu suspenso novamente, clique fora, ou escolha uma linha para fechá-lo. Enquanto renomear ou propriedades estiver aberto, o painel não se fecha ao perder o foco.

:::figure{side=center width=320}
![Painel do gerenciador de lista](ui/placeholder.png)
Menu suspenso de lista → painel do gerenciador de lista (placeholder).
:::

### Rolagem {#scroll-lists}

- **Rolagem no menu suspenso** — avança a imagem atual daquele lado sem abrir o painel.
- **Rolagem no canvas** — avança o lado sob o cursor; `Shift` + rolagem avança os dois lados. Regras completas: [Comparação → Percorrer imagens com a rolagem](help://comparison#scroll-images).
- **Rolagem na avaliação** — altera apenas a nota da linha, não o índice atual.

### Linhas {#rows}

- **Selecionar** — clique em uma linha para torná-la a atual; o painel fecha e o canvas é atualizado.
- **Reordenar** — arraste dentro de uma mesma lista.
- **Mover entre listas** — arraste uma linha para fora do painel único para expandir o modo duplo, depois solte na outra lista.
- **Dica de caminho** — passe o mouse sobre um nome truncado para ver o caminho completo.

### Avaliação {#rating}

Cada linha tem um chip de avaliação. Use menos / mais, ou role sobre o chip, sem sair do painel.

### Menu de contexto {#context-menu}

- **Linha da lista** — renomear, copiar caminho, propriedades, ou remover.
- **Canvas (quadro atual)** — mesmo menu, mais duplicar; renomear é exclusivo da lista.

Propriedades abre [Propriedades da Imagem](help://image_properties).

### Botões da barra de ferramentas {#quick-list-actions}

- **Adicionar arquivos** — botão ao lado de cada menu suspenso; adiciona apenas àquele lado.
- **Trocar** (`X`) — clique curto troca o par atual; clique longo troca as duas listas.
- **Remover** — clique curto descarta o quadro atual daquele lado; clique longo limpa a lista inteira daquele lado.

### Carregamento {#loading}

Arrastar e soltar na janela pergunta qual lista deve receber os arquivos. `Ctrl+V` cola uma imagem da área de transferência e pode mostrar uma sobreposição de lado — veja [Arquivos e Projetos](help://file_management).

### Painel de configurações de rótulo {#toolbar-flyouts}

{{tr:image_compare.action.text_settings}} (ou clique com o botão direito em {{tr:image_compare.action.file_names}}) abre um painel para tamanho, peso, cores e posicionamento. Feche com `Esc` ou um clique fora. A cor do divisor usa um seletor de cor, não um painel — veja [Comparação](help://comparison). Painéis de opções da lupa: [Lupa](help://magnifier).

:::figure{side=left width=280}
![Painel de configurações de rótulo](ui/placeholder.png)
{{tr:image_compare.action.text_settings}} (placeholder).
:::

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

Uma sessão {{tr:workspace.session_types.multi_compare}} não tem painel de lista dupla — as imagens vão para slots na grade. As configurações de texto do rótulo ainda abrem um painel (sem os botões de posicionamento do {{tr:workspace.session_types.image_compare}}). Detalhes: [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
