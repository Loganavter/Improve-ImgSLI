## Editor de vídeo

Grave uma sessão **Comparar imagens** como trilhas de controle ao vivo, ajuste a linha do tempo e codifique o resultado em vídeo ou GIF. Para exportar imagens estáticas, use [Exportação](help://workspace.export).

### Gravar uma sessão {#recording}

- **Gravar vídeo** (`R`) — inicia a gravação das ações do canvas; **Pausar gravação** a interrompe temporariamente e o mesmo controle encerra a captura.
- **O que é armazenado** — as ações do canvas ao longo do tempo (zoom, panorâmica, divisor, lupa, imagens carregadas e configurações relacionadas) são salvas como trilhas de controle com pontos de amostra, e não como uma captura bruta da tela; por isso é possível reajustar cada controle na linha do tempo depois.
- **Taxa de captura** — definida pelo **FPS de Gravação** nas [Configurações](help://platform.settings#image_compare); mais quadros por segundo deixam o movimento mais fluido e a gravação mais pesada.

### Abrir o editor {#open-editor}

Depois de parar a gravação, abra o **Editor de vídeo** (`Ctrl+E`) para percorrer os quadros, recortar o intervalo e exportar. Os controles do editor também aparecem em **Localizar ação**.

### Edição da linha do tempo {#timeline}

- **Percorrer** — arraste o cursor de tempo para navegar pelos quadros.
- **Intervalo** — `Shift` + arrastar marca um trecho; as alças e o meio da seleção se movem separadamente; **Cortar para Seleção** mantém só o trecho marcado e descarta o resto.
- **Excluir** — `Delete` ou `Backspace` removem o intervalo selecionado.
- **Reproduzir** — `Space` inicia e pausa a reprodução; desfaça com `Ctrl+Z` e refaça com `Ctrl+Y`.

:::figure{side=block width=840}
![Linha do tempo de vídeo](../assets/video_timeline.jpg)
Editor de vídeo — linha do tempo.
:::

### Trilhas e o que foi capturado {#tracks}

As trilhas de ferramentas (divisor, lupa, área visível e similares) mostram como os controles gravados mudam no tempo. Entre os pontos de amostra, o editor interpola os valores para a reprodução acompanhar a sessão ao vivo. A lupa grava a posição de captura (o anel de captura na imagem) e o deslocamento da lente em relação à captura como trilhas separadas.

### Qualidade da pré-visualização {#preview-quality}

**Qualidade do Preview** reduz apenas a qualidade da pré-visualização dentro do editor, para a edição responder mais rápido. O arquivo final não muda.

- **Completa (1.0x)** — pré-visualização mais nítida e mais pesada para a máquina; é o padrão.
- **Equilibrada (0.75x)** — bom equilíbrio entre nitidez e fluidez, indicado para a maioria das sessões.
- **Desempenho (0.5x)** — pré-visualização mais leve, útil quando a varredura fica lenta.
- **Rascunho (0.25x)** — pré-visualização mais rápida e com menos detalhe, para máquinas mais lentas.

### Exportar vídeo ou GIF {#export-encode}

- **Quadro** — define a resolução (bloqueie a proporção para manter o enquadramento), o FPS (não pode passar do **FPS de Gravação**) e o enquadramento: ajustar a imagem ao quadro ou recortá-la; a cor de preenchimento cobre bordas vazias.
- **Codec** — escolha o contêiner e o codec na aba padrão; os codificadores de hardware só aparecem quando o sistema oferece.
- **Qualidade** — escolha entre CRF/CQ e taxa de bits e ajuste as predefinições relacionadas.
- **Caminho** — indica o arquivo de saída; os botões de pasta favorita reutilizam a última pasta escolhida.
- **Progresso** — mostra o andamento da codificação; pode ser interrompido, e o log registra as mensagens do codificador.

:::figure{side=block width=630}
![Painel de exportação de vídeo](../assets/video_export.jpg)
Editor de vídeo — exportação.
:::

### CLI Manual {#manual-cli}

A aba **CLI Manual** repassa argumentos brutos do FFmpeg quando a aba padrão não cobre o caso. Use-a apenas se souber os parâmetros: valores incorretos podem gerar um arquivo inválido ou falhar a codificação.

### Próximos tópicos {#next-topics}

- Para exportar imagens estáticas, veja [Exportação](help://workspace.export).
- [Comparação](help://workspace.image_compare.comparison) e [Lupa](help://workspace.image_compare.magnifier) mostram os modos de diferença e a lente que acompanham a gravação.
