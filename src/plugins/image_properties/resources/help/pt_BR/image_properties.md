## Propriedades da imagem

Metadados do arquivo e contexto no aplicativo para uma imagem carregada. O diálogo flutua sobre a sessão e nada muda nela.

### Abrir o diálogo {#open}

O item {{tr:image_compare.action.context_properties}} no menu de contexto de uma lista ou célula abre {{tr:image_properties.title}} para aquela imagem.

:::figure{side=block width=280}
![Diálogo de propriedades da imagem](../assets/platform/image_properties.png)
{{tr:image_properties.title}}.
:::

### Seções {#sections}

As linhas vêm agrupadas em:

- {{tr:image_properties.section_file}} — nome, caminho, tamanho em disco, formato, data de modificação
- {{tr:image_properties.section_image}} — tamanho em pixels, proporção, orientação, canais, modo / perfil de cor quando houver
- {{tr:image_properties.section_app}} — como o aplicativo posiciona a imagem na sessão atual (abaixo)
- {{tr:image_properties.section_metadata}} — campos de câmera / EXIF quando o arquivo os fornece

Linhas sem valor são omitidas; um erro de leitura aparece como {{tr:image_properties.read_error}}.

### Contexto no aplicativo {#in-app}

{{tr:image_properties.section_app}} depende do tipo de sessão. Um item {{tr:workspace.session_types.image_compare}} traz {{tr:image_properties.side}} (esquerda / direita) e {{tr:image_properties.rating}}. Uma célula {{tr:workspace.session_types.multi_compare}} traz {{tr:image_properties.position}}. Essas linhas descrevem o estado da sessão, não o arquivo em disco.

### Fechar {#close}

{{tr:image_properties.close}} dispensa o diálogo. {{tr:image_properties.copy_all}} copia todas as linhas visíveis para a área de transferência; linhas individuais têm a própria cópia.
