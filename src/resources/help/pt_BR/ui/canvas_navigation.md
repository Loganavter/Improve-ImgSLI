## Navegação no Canvas

Movimento dentro do canvas de comparação: zoom centrado no cursor, pan com o botão do meio, `Space` para pré-visualização de um lado inteiro.

### Zoom e panorâmica {#zoom}

- **Zoom** — `Ctrl` + roda do mouse sobre o canvas; centrado no cursor.
- **Panorâmica** — botão do meio do mouse + arraste, mesmo em `100%` de zoom.
- **Modo** — sem ferramenta de navegação separada; os gestos funcionam direto no canvas ativo.

:::figure{side=block width=280}
![Zoom e panorâmica no canvas]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → canvas.
:::

### Pré-visualização rápida de lado {#quick-side-preview}

- **Lado 1** — `Space` + `LMB`.
- **Lado 2** — `Space` + `RMB`.
- **Soltar** — retorno à divisão normal.
- **Com lupa combinada** — `Space+Shift` força um lado dentro da lente.

### Durante o zoom {#zoom-side-effects}

- **Rótulos de nome de arquivo** — visíveis apenas em `100%` de zoom; reaparecem ao ajustar.
- **Linha de divisão** — mantém uma posição estável na tela conforme o zoom muda.
- **Qualidade** — o cache de pré-visualização e a interpolação estão em [Configurações → Desempenho](help://settings#performance).
