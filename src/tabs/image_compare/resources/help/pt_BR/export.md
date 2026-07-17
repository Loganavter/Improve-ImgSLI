## Exportação

Salve o que você vê como uma imagem estática. Gravação e o editor de vídeo têm o próprio tópico: [Editor de vídeo](help://video).

### Salvar uma imagem {#saving-an-image}

{{tr:image_compare.action.save}} (`Ctrl+Shift+S`) abre o diálogo de exportação.

- **Caminho** — pasta de saída e nome do arquivo.
- **Formato** — PNG, JPEG, WEBP, BMP, TIFF ou JXL.
- **Pré-visualização** — o painel ao vivo mostra o resultado composto antes de gravar o arquivo.

:::figure{side=right width=280}
![Diálogo de exportação](ui/placeholder.png)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}} (placeholder).
:::

### Resolução e qualidade {#resolution-and-quality}

- **Tamanho** — largura e altura quando o tamanho da origem é conhecido; o bloqueio mantém a proporção.
- **Qualidade** — {{tr:label.quality}} para formatos com perda.
- **PNG** — nível de compressão e {{tr:export.optimize_png}}.
- **Preenchimento** — formatos transparentes podem ativar {{tr:export.fill_background}} e escolher uma cor de fundo.

### Metadados e favoritos {#metadata-and-favorites}

- **Metadados** — {{tr:export.include_metadata}}; comentário opcional e {{tr:export.remember_by_default}}.
- **Favoritos** — {{tr:misc.set_as_favorite}} / {{tr:tooltip.use_favorite}} após navegar por uma pasta.
- **Rótulos** — quando {{tr:image_compare.action.file_names}} está ligado, os nomes podem ser gravados na imagem.

### Salvamento rápido {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} com as últimas configurações de exportação.
- **`Ctrl+Shift+S`** — sempre abre o diálogo.
- **Bandeja** — acesso opcional ao último salvamento em [Configurações → Geral](help://settings#general).

### Gravação e vídeo {#video-editor}

Para capturar uma sessão e codificar vídeo ou GIF, veja [Editor de vídeo](help://video). Imagens estáticas e vídeo mantêm paridade visual com o canvas ao vivo (incluindo modos de diferença).
