## Propriedades da Imagem

Inspecione os metadados do arquivo e o contexto dentro do aplicativo para uma imagem carregada, sem sair da sessão.

### Abrir o diálogo {#open}

Clique com o botão direito em uma linha de uma lista {{tr:workspace.session_types.image_compare}}, ou em um slot {{tr:workspace.session_types.multi_compare}}, e escolha {{tr:image_properties.title}}. O diálogo é somente leitura, exceto {{tr:image_properties.copy_all}}, que copia todas as linhas visíveis para a área de transferência.

:::figure{side=right width=280}
![Diálogo de Propriedades da Imagem](ui/placeholder.png)
{{tr:image_properties.title}} (placeholder).
:::

### Seções {#sections}

As linhas são agrupadas em:

- {{tr:image_properties.section_file}} — nome, caminho, tamanho no disco, formato, data de modificação
- {{tr:image_properties.section_image}} — tamanho em pixels, proporção, orientação, canais, modo de cor / perfil quando disponível
- {{tr:image_properties.section_app}} — como o aplicativo posiciona essa imagem na sessão atual (veja abaixo)
- {{tr:image_properties.section_metadata}} — campos de câmera / EXIF quando o arquivo os fornece

Valores ausentes ficam em branco; um erro de leitura do arquivo é exibido como {{tr:image_properties.read_error}}.

### Contexto no aplicativo {#in-app}

{{tr:image_properties.section_app}} depende do tipo de sessão. Uma sessão {{tr:workspace.session_types.image_compare}} pode mostrar {{tr:image_properties.side}} (esquerda / direita) e {{tr:image_properties.rating}}. Já {{tr:workspace.session_types.multi_compare}} pode mostrar {{tr:image_properties.position}} ou {{tr:image_properties.slot}} da célula. Essas linhas descrevem o estado da sessão, não o arquivo em disco.

### Fechar {#close}

{{tr:image_properties.close}} fecha o diálogo. Fechar não altera listas, avaliações ou o canvas.
