## Comparação

Compare duas imagens no canvas inteiro com um divisor móvel, rótulos de nome opcionais, visualizações por canal e modos de diferença — sem abrir a lupa.

### Linha divisória {#split-line}

Com a lupa desligada, arraste o divisor sobre o par.

- **Orientação** — {{tr:image_compare.action.divider_orientation}} alterna horizontal / vertical.
- **Largura** — role sobre {{tr:image_compare.action.divider_width}}.
- **Cor** — {{tr:image_compare.action.divider_color}}.
- **Visibilidade** (`D`) — {{tr:image_compare.action.divider_visible}} mostra ou oculta a linha.
- **Combinado** — {{tr:image_compare.action.divider_combined}} reúne orientação, largura e cor (rolagem / clique direito / clique do meio); veja a dica do controle.

:::figure{side=block width=280}
![Linha divisória]({{img:workspace.image_compare.comparison.split_line}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.divider}}.
:::

### Percorrer imagens com a rolagem {#scroll-images}

- **Rolagem no canvas** — avança a lista do lado sob o cursor (à esquerda de um divisor vertical / acima de um horizontal = lado 1; a outra metade = lado 2).
- **`Shift` + rolagem** — avança as duas listas juntas.
- **Pré-visualização de uma imagem** — a rolagem sempre avança o lado visível.
- **Rolagem no menu suspenso** — avança aquele lado sem abrir o painel; veja [Listas e Painéis](help://ui.lists_flyouts#scroll-lists).
- **Trocar** (`X`) — clique curto troca o par atual; pressionamento longo troca as duas listas.

### Rótulos {#labels-and-metrics}

- **Mostrar nomes** (`N`) — {{tr:image_compare.action.file_names}}; podem ser gravados nas exportações quando ativados.
- **Zoom** — os rótulos ficam ocultos enquanto o zoom não é `100%` e voltam no zoom de ajuste.
- **Configurações de texto** — {{tr:image_compare.action.text_settings}} abre um painel para tamanho, peso, opacidade, cores, fundo e posicionamento.

### Métricas {#metrics}

- **{{tr:ui.psnr}} / {{tr:ui.ssim}}** — desligados por padrão; ative o cálculo automático em [Configurações → Análise](help://settings#analysis).
- **Propriedades** — [Propriedades da imagem](help://image_properties) pelo menu de contexto de uma linha da lista (metadados do arquivo e lado / avaliação na sessão).
- **Mover** — o menu de contexto no canvas ou na lista coloca um fantasma de arraste sob o ponteiro (pendurado à esquerda e abaixo); mova um pouco e clique em outra aba da área de trabalho (ou no canvas) para iniciar o mesmo fluxo de inserção do Duplicar / colar. `Esc` ou clique direito cancela.

### Modos de canal {#channel-modes}

{{tr:image_compare.action.channel_mode}} (`C`) cicla RGB, R, G, B e luminância para inspecionar um canal sem sair do canvas.

### Modos de diferença {#difference-modes}

{{tr:image_compare.action.diff_mode}} (`H` cicla) destaca onde o par difere:

:::figure{side=block width=280}
![Modo de diferença]({{img:workspace.image_compare.comparison.difference_modes}})
{{tr:image_compare.action.diff_mode}}.
:::

- **{{tr:image_compare.action.diff_highlight}}** — regiões de mudança no par ao vivo
- **{{tr:image_compare.action.diff_grayscale}}** — dessatura diferenças de intensidade
- **{{tr:image_compare.action.diff_edges}}** — diferença orientada a bordas
- **{{tr:image_compare.action.diff_ssim}}** — mapa de similaridade estrutural quando as métricas suportam

Canvas ao vivo, imagens exportadas e gravação de vídeo mantêm a mesma aparência. Os modos de diferença combinam com as visualizações de canal. Para inspeção local, use a [Lupa](help://magnifier).
