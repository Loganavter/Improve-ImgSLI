---
description: Transformar uma comparação ao vivo em vídeo ou GIF editado.
icon: video.svg
---
## Editor de vídeo

O Editor de vídeo grava uma sessão ao vivo do **Comparar imagens** como trilhas das ferramentas usadas, depois recorta a linha do tempo e codifica o resultado em vídeo ou GIF. Imagens estáticas ficam em [Exportação](help://workspace.export).

### Gravar uma sessão {#recording}

- **Gravar vídeo** (`R`) — inicia e para a gravação; **Pausar gravação** pausa e retoma.
- A gravação armazena as ações no canvas ao longo do tempo — zoom e panorâmica, o divisor, a lupa, as imagens carregadas e as configurações relacionadas — como trilhas com pontos de gravação, e não como uma captura bruta da tela.
- **FPS de Gravação** — a taxa de quadros da gravação, definida em **Comparar imagens** nas [Configurações](help://platform.settings#image_compare).

### Abrir o editor {#open-editor}

**Editor de vídeo** (`Ctrl+E`) abre uma janela onde é possível percorrer quadros, editar o intervalo e exportar. As ações do editor também aparecem em **Localizar ação**.

### Edição da linha do tempo {#timeline}

- **Percorrer** — arraste o cursor de tempo para avançar pela gravação.
- **Intervalo** — `Shift` + arrastar marca um trecho; as alças das pontas e o meio da seleção se movem de forma independente. **Cortar para Seleção** remove o trecho marcado e une o restante.
- **Excluir** — `Delete` / `Backspace` removem o intervalo selecionado.
- **Reproduzir** — `Space` inicia e pausa a reprodução; `Ctrl+Z` / `Ctrl+Y` desfazem e refazem edições.

:::figure{side=block width=100%}
![Linha do tempo de vídeo](../assets/video_timeline.jpg)
A linha do tempo: trilhas com seus pontos, a tira de quadros acima e a régua de tempo abaixo.
:::

### Trilhas e o que foi capturado {#tracks}

O editor mostra cada ferramenta gravada como uma trilha própria — o divisor, a lupa, a área visível e similares — para acompanhar quando cada elemento mudou durante a sessão. Entre os pontos de gravação, o editor interpola os valores, para a reprodução coincidir com a sessão ao vivo. Para a lupa, a trilha **Capture Position** registra onde o **Anel de captura** fica na imagem, e a trilha **Offset** registra o quanto a lente se desloca da captura. Para mudar o resultado, recorte ou exclua trechos na [linha do tempo](help://workspace.image_compare.video#timeline) e use desfazer ou refazer.

### Qualidade da pré-visualização {#preview-quality}

**Qualidade do Preview** reduz apenas a pré-visualização dentro do editor, para manter o editor responsivo; ela não altera o arquivo final.

- **Completa (1.0x)** — a pré-visualização mais nítida, mas a mais pesada para a máquina; é o padrão.
- **Equilibrada (0.75x)** — um equilíbrio mais leve, adequado à maioria das sessões.
- **Desempenho (0.5x)** — use quando a varredura ficar lenta.
- **Rascunho (0.25x)** — a pré-visualização mais rápida, com menos detalhe.

### Exportar vídeo ou GIF {#export-encode}

- **Quadro** — define a resolução de saída (bloqueie a proporção se necessário), a taxa de quadros (que não pode passar do **FPS de Gravação**) e se a imagem é ajustada ou recortada, com uma cor de preenchimento opcional para as bordas vazias.
- **Codec** — escolhe o contêiner e o codec na aba padrão; codificadores de hardware só aparecem quando o sistema os expõe.
- **Qualidade** — define o valor CRF/CQ ou a taxa de bits, com as predefinições relacionadas.
- **Caminho** — define o arquivo de saída; os botões de pasta favorita reutilizam a última pasta preferida.
- **Progresso** — mostra o andamento da codificação; é possível interrompê-la, e o log registra as mensagens do codificador.

:::figure{side=block width=100%}
![Painel de exportação de vídeo](../assets/video_export.jpg)
O painel de exportação: a pré-visualização do quadro à esquerda e as configurações do codificador à direita.
:::

### CLI Manual {#manual-cli}

**CLI Manual** repassa argumentos brutos de saída do FFmpeg quando a aba padrão não basta. Esse modo ignora a validação das opções feita pelo editor, então um argumento incorreto faz a codificação falhar em vez de ser interceptado na interface.

### Próximos tópicos {#next-topics}

Imagens estáticas: [Exportação](help://workspace.export). Os modos de diferença e a lupa durante a gravação coincidem com o canvas ao vivo — [Comparação](help://workspace.image_compare.comparison) e [Lupa](help://workspace.image_compare.magnifier).
