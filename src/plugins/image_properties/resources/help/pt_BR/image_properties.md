## Propriedades da imagem

O diálogo **Propriedades** mostra os dados do arquivo e como a imagem é usada na sessão atual. Ele apenas exibe informações e não altera nada na sessão.

### Abrir o diálogo {#open}

Clique com o botão direito em uma imagem na lista ou no slot e escolha **Propriedades**.

:::figure{side=block width=280}
![Diálogo de propriedades da imagem](../assets/platform/image_properties.png)
O diálogo **Propriedades**: as linhas são agrupadas por origem, por exemplo **Arquivo** e **Metadados**.
:::

### O que é mostrado {#sections}

As linhas são agrupadas em:

- **Arquivo** — nome, caminho, tamanho em disco, formato e data de modificação.
- **Imagem** — tamanho em pixels, proporção, orientação e canais; modo e perfil de cor quando o arquivo os fornece.
- **No aplicativo** — como o aplicativo usa a imagem na sessão atual (veja abaixo).
- **Metadados** — campos de câmera e EXIF quando o arquivo os fornece.

Linhas sem valor são omitidas. Se o arquivo não puder ser lido, em vez dos dados aparece **Erro de leitura**.

### Contexto no aplicativo {#in-app}

O grupo **No aplicativo** depende do tipo de sessão:

- Em uma sessão **Comparar imagens**, mostra **Lado** (esquerdo ou direito) e **Avaliação**.
- Em uma sessão **Comparação múltipla**, mostra a **Posição** da célula.

Essas linhas descrevem o estado da sessão, não o arquivo em disco.

### Fechar {#close}

**Fechar** dispensa o diálogo. **Copiar tudo** copia todas as linhas visíveis para a área de transferência; o texto selecionado pode ser copiado pelo menu de contexto.
