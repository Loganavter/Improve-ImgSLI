## Botões e Controles

A **Barra de ferramentas** reúne as ferramentas da sessão ativa, e a configuração **Modo da UI** decide quantas ações compartilham um mesmo controle.

### A barra de ferramentas {#toolbar}

A **Barra de ferramentas** é a faixa de controles de ícone da sessão ativa. Cada controle liga ou desliga um recurso, ajusta um valor numérico ou abre um painel ou diálogo. O conjunto de controles vem da aba, então a faixa muda ao trocar de aba.

:::figure{side=block height=107}
![Barra de ferramentas da sessão](../../assets/ui/toolbar.jpg)
A barra de ferramentas acima do canvas; o conjunto de ícones muda com a sessão ativa.
:::

### Modos de interface {#ui-modes}

As mesmas ferramentas aparecem em todos os **Modo da UI**; só o leiaute muda. Menos controles por modo significam menos cliques, mas mais combinações acumuladas em cada controle. Escolha um modo na primeira execução, ou troque depois em [Configurações](help://platform.settings#interface) → **Aparência**.

#### Iniciante {#mode-beginner}

O modo padrão: cada controle faz uma tarefa, então as ferramentas se espalham por mais botões de função única.

:::figure{side=block height=65}
![Leiaute iniciante da barra](../../assets/ui/mode_beginner.png)
Leiaute **Iniciante**: as mesmas ferramentas distribuídas em mais botões, um por tarefa.
:::

#### Avançado {#mode-advanced}

Menos ícones. Alguns controles combinam um clique curto com a rolagem — por exemplo, orientação e espessura no mesmo controle.

:::figure{side=block height=65}
![Leiaute avançado da barra](../../assets/ui/mode_advanced.png)
Leiaute **Avançado**: controles relacionados compartilham um ícone, unindo clique e rolagem.
:::

#### Especialista {#mode-expert}

A faixa mais densa: um único controle combina clique, rolagem e os demais botões do mouse.

:::figure{side=block height=65}
![Leiaute especialista da barra](../../assets/ui/mode_expert.png)
Leiaute **Especialista**: o menor número de ícones, cada um unindo clique, rolagem e os demais botões do mouse.
:::

### Controles com várias ações {#multi-action}

Em **Avançado** e, principalmente, em **Especialista**, o mesmo ícone costuma fazer mais de uma coisa:

- **Clique curto** — ação principal ou alternância.
- **Rolagem** — ajusta um valor numérico sem abrir um diálogo.
- **Clique longo** — variante mais forte em alguns botões de lista (limpar a lista inteira; trocar as duas listas).
- **Outros botões do mouse** — em **Especialista**, por exemplo o botão direito para escolher a cor ou o botão do meio para ocultar ou restaurar o **Divisor** em um controle compacto.

O **Iniciante** separa as combinações de clique com rolagem em controles separados de função única; o clique longo dos botões de lista funciona em todos os modos.

:::figure{side=block height=44}
![Clique longo em um botão de lista](../../assets/ui/long_press.png)
Um botão de lista: o clique curto executa a ação comum e o clique longo a variante mais forte.
:::

### Encontrar um controle pelo nome {#find-action}

**Localizar ação** (`Ctrl+Shift+P`) encontra toda ação por parte do rótulo, inclusive as que não têm botão visível. `Ctrl+Enter` em uma linha abre **Saiba mais** quando a linha tem um tópico de ajuda.
