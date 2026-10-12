## Listas e Painéis

Os menus suspensos abrem painéis dentro da janela, sobre a janela principal. Um clique fora ou `Esc` fecha o painel. Layout da barra e gestos multi-ação: [Botões e Controles](help://ui.buttons). Estilo dos rótulos de nome de arquivo: [Comparação](help://comparison).

### Gerenciador de lista {#list-manager}

Em uma sessão {{tr:workspace.session_types.image_compare}}, cada lado tem um menu suspenso de lista. Um clique abre o painel de gerenciamento de lista daquele lado (linhas, avaliações, arraste). O painel permanece fechado se a lista estiver vazia. O mesmo menu suspenso, um clique fora ou a escolha de uma linha fecha o painel. Enquanto renomear ou propriedades estiver aberto, o painel não se fecha ao perder o foco.

:::figure{side=block width=320}
![Painel do gerenciador de lista]({{img:ui.lists_flyouts.list_manager}})
Menu suspenso de lista → painel do gerenciador de lista.
:::

### Rolagem {#scroll-lists}

- **Rolagem no menu suspenso** — avança a imagem atual daquele lado sem abrir o painel.
- **Rolagem no canvas** — avança o lado sob o cursor; `Shift` + rolagem avança os dois lados. Regras completas: [Comparação → Percorrer imagens com a rolagem](help://comparison#scroll-images).
- **Rolagem na avaliação** — altera apenas a nota da linha, não o índice atual.

### Linhas {#rows}

- **Selecionar** — um clique em uma linha a torna a atual; o painel fecha e o canvas é atualizado.
- **Seleção múltipla** — `Ctrl`/`Cmd`+clique alterna linhas; arrastar sobre o espaço vazio do painel desenha um laço. Arrastar qualquer linha selecionada move o conjunto.
- **Reordenar** — arraste dentro de uma mesma lista.
- **Mover entre listas** — arrastar para fora do painel único expande o modo duplo; soltar na outra lista move as linhas.
- **Dica de caminho** — passar o mouse sobre um nome truncado mostra o caminho completo.

### Avaliação {#rating}

Cada linha tem um chip de avaliação. Os botões de menos / mais ou a rolagem sobre o chip alteram a nota sem sair do painel.

### Menu de contexto {#context-menu}

- **Linha da lista** — renomear, copiar caminho, propriedades, mover, recorte ou remover.
- **Canvas (quadro atual)** — copiar caminho, duplicar, propriedades, mover, recorte e remover; renomear é exclusivo da lista.

Propriedades abre [Propriedades da Imagem](help://image_properties).

### Botões da barra de ferramentas {#quick-list-actions}

- **Adicionar arquivos** — botão ao lado de cada menu suspenso; adiciona apenas àquele lado.
- **Trocar** (`X`) — clique curto troca o par atual; clique longo troca as duas listas.
- **Remover** — clique curto descarta o quadro atual daquele lado; clique longo limpa a lista inteira daquele lado.

### Carregamento {#loading}

Soltar arquivos na janela os coloca na lista do lado sob o cursor. `Ctrl+V` cola uma imagem da área de transferência e pode mostrar uma sobreposição de lado — veja [Arquivos e Projetos](help://file_management).

### Painel de configurações de rótulo {#toolbar-flyouts}

O painel abre por {{tr:image_compare.action.text_settings}} ou com o botão direito em {{tr:image_compare.action.file_names}}; `Esc` ou um clique fora fecha o painel.

No painel: tamanho da fonte, peso, opacidade, cores do texto e do fundo, desenhar fundo e posição do rótulo (bordas / linha de divisão).

:::figure{side=block width=280}
![Painel de configurações de rótulo]({{img:ui.lists_flyouts.toolbar_flyouts}})
{{tr:image_compare.action.text_settings}}.
:::

A cor da linha de divisão e os painéis da lupa ficam em outro lugar — [Comparação](help://comparison) e [Lupa](help://magnifier).

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

Uma sessão {{tr:workspace.session_types.multi_compare}} não tem painel de lista dupla — as imagens vão para slots na grade. As configurações de texto do rótulo ainda abrem um painel (sem os botões de posicionamento do {{tr:workspace.session_types.image_compare}}). Detalhes: [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
