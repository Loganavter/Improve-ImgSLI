## Lupa

A lupa amostra uma região das imagens comparadas e mostra uma vista ampliada no canvas. Use-a quando a linha divisória sozinha não basta para um detalhe local.

### Ativar {#enabling}

- **Alternar** — {{tr:image_compare.action.magnifier}} na barra de ferramentas, ou `M`.
- **Posicionar** — clique ou arraste na imagem para definir a área de captura (círculo vermelho).
- **Anel** — tamanho e cor do anel de captura seguem o estilo da lente.

:::figure{side=right width=280}
![Lente da lupa](magnifier/placeholder.png)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.magnifier}} (placeholder).
:::

### Tamanho e movimento {#size-and-movement}

- **Tamanho da lente** — {{tr:label.magnifier_size}}.
- **Tamanho da captura** — {{tr:label.capture_size}} (quanto da área de origem é amostrada).
- **Mover** — `WASD` com a lente ativa; `QE` ajusta o espaçamento quando as metades estão separadas.
- **Velocidade** — no painel da lupa quando ele está visível.

### Congelar {#freeze}

{{tr:image_compare.action.freeze}} (`F`) trava a lente na tela para você ajustá-la com o teclado enquanto o ponteiro fica livre.

### Divisor, guias e cores {#guides-and-colors}

- **Orientação** — {{tr:image_compare.action.magnifier_orientation}}.
- **Divisor interno** — {{tr:image_compare.action.magnifier_divider_combined}} (rolagem / clique direito).
- **Visibilidade** — {{tr:image_compare.action.magnifier_divider_visible}} e {{tr:image_compare.action.magnifier_guides}}, além das larguras.
- **Cores** — {{tr:image_compare.action.magnifier_colors}} para cores de contorno por instância.

### Várias instâncias {#instances}

- **Adicionar / remover** — {{tr:image_compare.action.magnifier_instances}} para observar várias regiões.
- **Cor automática** — novas instâncias podem receber cores distintas quando a opção estiver ligada em Configurações.

### Modo combinado {#combined-mode}

- **Mesclar** — quando as metades ficam próximas o bastante, ou um modo de diferença está ativo, tornam-se uma só lente.
- **Divisão interna** — arraste com `RMB` dentro da lente.
- **Pré-visualização de lado** — `Space+Shift` pode forçar a pré-visualização de um lado com a lente ativa.

Para comparar o canvas inteiro sem a lente, veja [Comparação](help://comparison).

:::figure{side=right width=280}
![Lupa combinada](magnifier/placeholder.png)
{{tr:image_compare.action.magnifier}} modo combinado (placeholder).
:::

### Configurações que afetam a lupa {#related-settings}

Em [Configurações → Desempenho](help://settings#performance):

- Otimizar movimento da lupa e sua interpolação
- Destaque de interseção entre lentes
- Cor automática para novas instâncias

Os limites do cache de exibição valem só para a pré-visualização principal — a lupa ainda amostra os originais.
