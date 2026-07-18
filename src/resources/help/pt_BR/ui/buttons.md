## Botões e Controles

A barra de ferramentas fica acima da tela em uma sessão de comparação. Ela concentra as ferramentas da sessão — linha divisória, modos de visão, lupa, gravação — enquanto listas, adicionar/salvar e a engrenagem de configurações ficam no chrome ao redor.

### A barra de ferramentas {#toolbar}

- **Onde** — uma faixa de ícones acima da tela.
- **O quê** — alternâncias, ajustes de valor e botões que abrem painéis ou diálogos para o tipo de sessão ativo.
- **Quão densa** — depende de {{tr:settings.ui_mode}} (onboarding na primeira execução ou [Configurações → Aparência](help://settings#interface)).

:::figure{side=block height=107}
![Barra de ferramentas da sessão]({{img:ui.buttons.toolbar}})
Barra de ferramentas acima da tela.
:::

### Modos de interface {#ui-modes}

As mesmas ferramentas se organizam de forma diferente em cada {{tr:settings.ui_mode}}. Escolha o modo na primeira execução; depois altere em Configurações.

### {{tr:settings.ui_mode_beginner}} {#mode-beginner}

Mais botões separados — um controle ≈ uma tarefa. Amigável ao mouse; facilita achar cada ferramenta.

:::figure{side=block height=65}
![Layout iniciante da barra]({{img:ui.buttons.mode_beginner}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_beginner}}.
:::

### {{tr:settings.ui_mode_advanced}} {#mode-advanced}

Menos ícones. Alguns controles já combinam clique curto com rolagem (por exemplo orientação + espessura).

:::figure{side=block height=65}
![Layout avançado da barra]({{img:ui.buttons.mode_advanced}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_advanced}}.
:::

### {{tr:settings.ui_mode_expert}} {#mode-expert}

Faixa mais densa: um controle pode carregar clique, rolagem e outros botões do mouse para deixar mais espaço à imagem.

:::figure{side=block height=65}
![Layout especialista da barra]({{img:ui.buttons.mode_expert}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_expert}}.
:::

### Controles com várias ações {#multi-action}

Em {{tr:settings.ui_mode_advanced}} e sobretudo em {{tr:settings.ui_mode_expert}}, o mesmo ícone costuma fazer mais de uma coisa:

- **Clique curto** — ação principal ou alternância.
- **Rolagem** — ajusta um valor numérico (espessura do divisor, tamanho da lupa, …) sem abrir um diálogo.
- **Clique longo** — variante mais forte em alguns botões de lista (limpar a lista inteira; trocar as duas listas).
- **Outros botões do mouse** (especialista) — por exemplo clique direito para cor ou clique do meio para redefinir em controles compactos do divisor.

{{tr:settings.ui_mode_beginner}} mantém essas tarefas em botões separados em vez de empilhá-las.

:::figure{side=block height=44}
![Clique longo em um botão de lista]({{img:ui.buttons.long_press}})
Botão de lista — clique curto vs clique longo.
:::

### Exemplos no produto {#examples}

- **{{tr:workspace.session_types.image_compare}}** — nos modos mais densos, role a espessura do divisor ou o tamanho da lupa em um controle; clique longo limpa / troca nas listas. Detalhes: [Listas e Painéis](help://ui.lists_flyouts).
- **{{tr:workspace.session_types.multi_compare}}** — os mesmos hábitos de espessura / visibilidade nas linhas da grade (`D`).

### Encontrar um controle pelo nome {#find-action}

Pressione `Ctrl+Shift+P` ({{tr:menu.find_action}}), digite parte do rótulo e execute a ação, ou abra {{tr:action.palette.learn_more}} / `Ctrl+Enter` quando a linha tiver um tópico de ajuda.
