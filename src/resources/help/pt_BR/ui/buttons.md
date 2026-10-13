## Botões e Controles

A **Barra de ferramentas** fica acima do canvas em uma sessão de comparação. Ela reúne as ferramentas da sessão — **Divisor**, modos de exibição, **Lupa**, gravação — enquanto as listas, os controles de adicionar/salvar e a engrenagem de **Configurações** ficam na moldura da janela ao redor.

### A barra de ferramentas {#toolbar}

A **Barra de ferramentas** é a faixa de ícones da sessão ativa. Cada controle faz uma de três coisas: alterna um recurso, ajusta um valor numérico ou abre um painel ou diálogo. A quantidade de ícones exibidos depende do **Modo da UI** escolhido (veja [Configurações → Aparência](help://platform.settings#interface)).

:::figure{side=block height=107}
![Barra de ferramentas da sessão](../../assets/ui/toolbar.jpg)
A **Barra de ferramentas** acima do canvas; o conjunto de ícones muda com o tipo de sessão ativo.
:::

### Modos de interface {#ui-modes}

As mesmas ferramentas aparecem em todos os **Modo da UI**; o que muda é a organização. Menos controles por modo significam menos cliques, mas mais combinações empilhadas em cada controle. Você escolhe o modo na primeira execução e pode trocá-lo depois em [Configurações → Aparência](help://platform.settings#interface).

#### Iniciante {#mode-beginner}

Mais botões separados: cada controle faz uma coisa só.

:::figure{side=block height=65}
![Layout iniciante da barra](../../assets/ui/mode_beginner.png)
Layout **Iniciante**: as mesmas ferramentas distribuídas em mais botões, um por tarefa.
:::

#### Avançado {#mode-advanced}

Menos ícones. Alguns controles já combinam um clique curto com a rolagem — por exemplo, orientação e espessura no mesmo controle.

:::figure{side=block height=65}
![Layout avançado da barra](../../assets/ui/mode_advanced.png)
Layout **Avançado**: controles relacionados compartilham um ícone, unindo clique e rolagem.
:::

#### Especialista {#mode-expert}

A faixa mais densa: um único controle combina clique, rolagem e outros botões do mouse.

:::figure{side=block height=65}
![Layout especialista da barra](../../assets/ui/mode_expert.png)
Layout **Especialista**: o menor número de ícones, cada um reunindo clique, rolagem e os demais botões do mouse.
:::

### Controles com várias ações {#multi-action}

Em **Avançado** e, principalmente, em **Especialista**, o mesmo ícone costuma fazer mais de uma coisa:

- **Clique curto** — ação principal ou alternância.
- **Rolagem** — ajusta um valor numérico (espessura do **Divisor**, tamanho da **Lupa**, entre outros) sem abrir um diálogo.
- **Clique longo** — variante mais forte em alguns botões de lista (limpar a lista inteira; trocar as duas listas).
- **Outros botões do mouse** (em **Especialista**) — por exemplo, clique direito para escolher a cor ou clique do meio para redefinir um controle compacto do **Divisor**.

No **Iniciante**, essas tarefas ficam em botões separados em vez de empilhadas.

:::figure{side=block height=44}
![Clique longo em um botão de lista](../../assets/ui/long_press.png)
Um botão de lista: o clique curto executa a ação comum; manter pressionado executa a variante mais forte.
:::

### Exemplos no produto {#examples}

- Em uma sessão **Comparar imagens**, nos modos mais densos você rola a espessura do **Divisor** ou o tamanho da **Lupa** no mesmo controle, e um clique longo limpa ou troca as listas. Detalhes: [Comparação](help://workspace.image_compare.comparison).
- Em uma sessão **Comparação múltipla**, `D` alterna a **Visibilidade da grade** e o controle reúne o ajuste das **Linhas da grade**. Detalhes: [Visão Geral do Multi Compare](help://workspace.multi_compare.overview).

### Encontrar um controle pelo nome {#find-action}

Pressione `Ctrl+Shift+P` para abrir **Localizar ação**, digite parte do rótulo e execute a ação. Se a linha tiver um tópico de ajuda, `Ctrl+Enter` abre **Saiba mais**. Assim você alcança qualquer ação, inclusive as que não têm botão visível.
