## Navegação no Canvas

Movimento dentro do canvas de comparação: zoom centrado no cursor, pan com o botão do meio, `Space` para pré-visualização de um lado inteiro.

### Zoom e panorâmica {#zoom}

- **Zoom** — `Ctrl` + roda do mouse sobre o canvas.
- **Panorâmica** — botão do meio do mouse + arraste.
- **Ferramenta de navegação** — nenhuma; os gestos funcionam direto no canvas ativo.

:::figure{side=block width=280}
![Zoom e panorâmica no canvas]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → canvas.
:::

### Pré-visualização rápida de lado {#quick-side-preview}

Gesto do canvas de comparação (ver [Comparação](help://comparison)):

- **Lado esquerdo** — `Space` + `LMB`.
- **Lado direito** — `Space` + `RMB`.
- **Soltar** — volta à divisão normal.
- **Com lupa combinada** — `Space+Shift` força um lado dentro da lente (ver [Lupa](help://magnifier)).

### Durante o zoom {#zoom-side-effects}

- **Rótulos de nome de arquivo** — visíveis apenas em `100%` de zoom; reaparecem ao ajustar.
- **Linha de divisão** — posição fracionária (0–1); a fração se mantém ao mudar o zoom.
- **Qualidade de renderização** — interpolação no painel do canvas; backend em [Configurações → Desempenho](help://settings#performance).
