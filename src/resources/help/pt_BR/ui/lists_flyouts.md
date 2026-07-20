## Listas e Painéis

Os menus suspensos abrem painéis dentro da janela, sobre a janela principal. Trabalhe dentro do painel e depois feche com um clique fora ou `Esc`. Layout da barra e gestos multi-ação: [Botões e Controles](help://ui.buttons). Estilo dos rótulos de nome de arquivo: [Comparação](help://comparison).

### Gerenciador de lista {#list-manager}

Em uma sessão {{tr:workspace.session_types.image_compare}}, cada lado tem um menu suspenso de lista. Um clique abre o painel de gerenciamento de lista daquele lado (linhas, avaliações, arraste). O painel permanece fechado se a lista estiver vazia. Clique no mesmo menu suspenso novamente, clique fora, ou escolha uma linha para fechá-lo. Enquanto renomear ou propriedades estiver aberto, o painel não se fecha ao perder o foco.

:::figure{side=block width=320}
![Painel do gerenciador de lista]({{img:ui.lists_flyouts.list_manager}})
Menu suspenso de lista → painel do gerenciador de lista.
:::

### Rolagem {#scroll-lists}

- **Rolagem no menu suspenso** — avança a imagem atual daquele lado sem abrir o painel.
- **Rolagem no canvas** — avança o lado sob o cursor; `Shift` + rolagem avança os dois lados. Regras completas: [Comparação → Percorrer imagens com a rolagem](help://comparison#scroll-images).
- **Rolagem na avaliação** — altera apenas a nota da linha, não o índice atual.

### Linhas {#rows}

- **Selecionar** — clique em uma linha para torná-la a atual; o painel fecha e o canvas é atualizado.
- **Seleção múltipla** — `Ctrl`/`Cmd`+clique alterna linhas; arraste no espaço vazio do painel para um laço. Arrastar qualquer linha selecionada move o conjunto (o fantasma mostra a contagem).
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

Abrir: {{tr:image_compare.action.text_settings}} ou clique com o botão direito em {{tr:image_compare.action.file_names}}. Fechar: `Esc` ou clique fora.

No painel: tamanho da fonte, peso, opacidade, cores do texto e do fundo, desenhar fundo e posição do rótulo (bordas / linha de divisão).

:::figure{side=block width=280}
![Painel de configurações de rótulo]({{img:ui.lists_flyouts.toolbar_flyouts}})
{{tr:image_compare.action.text_settings}}.
:::

A cor da linha de divisão e os painéis da lupa ficam em outro lugar — [Comparação](help://comparison) e [Lupa](help://magnifier).

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

Uma sessão {{tr:workspace.session_types.multi_compare}} não tem painel de lista dupla — as imagens vão para slots na grade. As configurações de texto do rótulo ainda abrem um painel (sem os botões de posicionamento do {{tr:workspace.session_types.image_compare}}). Detalhes: [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
