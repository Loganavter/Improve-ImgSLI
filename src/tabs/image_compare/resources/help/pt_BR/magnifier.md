## Lupa

A lupa amostra uma região do par comparado e mostra uma vista ampliada no canvas — detalhe local além da linha divisória.

### Ativar {#enabling}

- **Alternar** — {{tr:image_compare.action.magnifier}} na barra de ferramentas, ou `M`.
- **Posicionar** — clique ou arraste na imagem para definir a área de captura (círculo vermelho).
- **Anel** — tamanho e cor do anel de captura seguem o estilo da lente.

:::figure{side=block width=280}
![Lente da lupa]({{img:workspace.image_compare.magnifier.enabling}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.magnifier}}.
:::

### Tamanho e movimento {#size-and-movement}

- **Tamanho da lente** — {{tr:image_compare.label.magnifier_size}}.
- **Tamanho da captura** — {{tr:image_compare.label.capture_size}} (quanto da área de origem é amostrada).
- **Mover** — `WASD` com a lente ativa; `QE` ajusta o espaçamento quando as metades estão separadas.
- **Velocidade** — no painel da lupa quando ele está visível.

### Congelar {#freeze}

{{tr:image_compare.action.freeze}} (`F`) trava a lente na tela; o ajuste pelo teclado continua ativo enquanto o ponteiro fica livre.

### Divisor, guias e cores {#guides-and-colors}

- **Orientação** — {{tr:image_compare.action.magnifier_orientation}}.
- **Divisor interno** — {{tr:image_compare.action.magnifier_divider_combined}} (rolagem / clique direito).
- **Visibilidade** — {{tr:image_compare.action.magnifier_divider_visible}} e {{tr:image_compare.action.magnifier_guides}}, além das larguras.
- **Cores** — {{tr:image_compare.action.magnifier_colors}} para cores de contorno por instância.

### Várias instâncias {#instances}

- **Adicionar / remover** — {{tr:image_compare.action.magnifier_instances}} para observar várias regiões.
- **Cor automática** — novas instâncias podem receber cores distintas quando a opção estiver ligada em Configurações.

### Modo combinado {#combined-mode}

- **Mesclar** — quando ambas as metades seguem visíveis e o espaçamento fecha no limiar de combinação, tornam-se uma só lente.
- **Divisão interna** — arraste com `RMB` dentro da lente.
- **Pré-visualização de lado** — `Space+Shift` força um lado dentro da lente combinada.

:::figure{side=block width=280}
![Lupa combinada]({{img:workspace.image_compare.magnifier.combined_mode}})
{{tr:image_compare.action.magnifier}} modo combinado.
:::

Para comparar o canvas inteiro sem a lente, veja [Comparação](help://workspace.image_compare.comparison).

### Configurações que afetam a lupa {#related-settings}

Opções relacionadas à lupa em [Configurações](help://platform.settings#image_compare):

- Otimizar movimento da lupa e sua interpolação
- Destaque de interseção entre lentes
- Cor automática para novas instâncias
