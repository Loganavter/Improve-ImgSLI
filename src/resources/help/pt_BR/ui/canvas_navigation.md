## Navegação no Canvas

Movimente-se dentro do canvas de comparação: aplique zoom em direção ao cursor, arraste com o botão do meio e mantenha `Space` pressionado para uma pré-visualização temporária de um lado inteiro.

### Zoom e panorâmica {#zoom}

- **Zoom** — mantenha `Ctrl` pressionado e role a roda do mouse sobre o canvas; o zoom é centrado no cursor.
- **Panorâmica** — mantenha o botão do meio do mouse pressionado e arraste, mesmo em `100%` de zoom.
- **Modo** — não há uma ferramenta de navegação separada; esses gestos funcionam direto no canvas ativo.

:::figure{side=right width=280}
![Zoom e panorâmica no canvas](ui/placeholder.png)
{{tr:workspace.session_types.image_compare}} → canvas (placeholder).
:::

### Pré-visualização rápida de lado {#quick-side-preview}

- **Lado 1** — mantenha `Space` pressionado, depois `LMB`.
- **Lado 2** — mantenha `Space` pressionado, depois `RMB`.
- **Soltar** — retorna à divisão normal.
- **Com lupa combinada** — mantenha `Space+Shift` para forçar um lado dentro da lente.

### Durante o zoom {#zoom-side-effects}

- **Rótulos de nome de arquivo** — visíveis apenas em `100%` de zoom; retornam automaticamente ao ajustar novamente.
- **Linha de divisão** — mantém uma posição estável na tela conforme o zoom muda.
- **Qualidade** — o cache de pré-visualização e a interpolação estão em [Configurações → Desempenho](help://settings#performance).
