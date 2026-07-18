## Editor de vídeo

Grave uma sessão {{tr:workspace.session_types.image_compare}} ao vivo, ajuste a linha do tempo e depois codifique para vídeo ou GIF. Imagens estáticas ficam em [Exportação](help://export).

### Gravar uma sessão {#recording}

- **Iniciar / pausar / parar** — {{tr:image_compare.action.record}} (`R`), {{tr:image_compare.action.pause_recording}}, depois pare pelos mesmos controles.
- **O que é armazenado** — ações do canvas ao longo do tempo (zoom/pan, divisor, lupa, imagens carregadas, configurações relacionadas) como trilhas de controle com pontos de amostra — não uma captura bruta da tela.
- **Taxa de captura** — [Configurações → Desempenho](help://settings#performance) ({{tr:settings.recording_fps}}).

### Abrir o editor {#open-editor}

Depois de parar, abra {{tr:image_compare.action.video_editor}} (`Ctrl+E`) para percorrer frames, editar o intervalo e exportar. Pesquisar controles do editor em {{tr:menu.find_action}} também abre este tópico de ajuda.

### Edição da linha do tempo {#timeline}

- **Percorrer** — arraste o cursor de tempo.
- **Intervalo** — `Shift`+arrastar marca um trecho; as alças e o meio da seleção movem-se à parte; {{tr:button.trim_to_selection}} mantém só essa seleção.
- **Excluir** — `Delete` / `Backspace` removem o intervalo selecionado.
- **Reproduzir** — `Space`; desfazer / refazer — `Ctrl+Z` / `Ctrl+Y`.

:::figure{side=block width=840}
![Linha do tempo de vídeo]({{img:workspace.image_compare.video.timeline}})
{{tr:image_compare.action.video_editor}} — linha do tempo.
:::

### Trilhas e o que foi capturado {#tracks}

As trilhas de ferramentas (divisor, lupa, viewport e similares) mostram como os controles gravados mudam no tempo. Entre os pontos de amostra o editor interpola os valores para a reprodução acompanhar a sessão ao vivo.

### Qualidade da pré-visualização {#preview-quality}

{{tr:video.preview_quality}} só reduz a pré-visualização dentro do editor para responsividade. A qualidade final da codificação não muda.

- **{{tr:video.preview_quality_full}}** — pré-visualização mais nítida; mais pesada na máquina.
- **{{tr:video.preview_quality_balanced}}** — equilíbrio padrão para a maioria das sessões.
- **{{tr:video.preview_quality_performance}}** — pré-visualização mais leve quando a varredura fica lenta.
- **{{tr:video.preview_quality_draft}}** — pré-visualização mais rápida; menos detalhe.

### Exportar vídeo ou GIF {#export-encode}

- **Quadro** — resolução (bloqueie a proporção se precisar), FPS (não acima do FPS de gravação), ajustar vs recortar; cor de preenchimento opcional para bordas vazias.
- **Codec** — contêiner e codec na aba padrão; codificadores de hardware aparecem só quando o sistema os expõe.
- **Qualidade** — CRF/CQ ou taxa de bits e predefinições relacionadas.
- **Caminho** — arquivo de saída; botões de pasta favorita reutilizam a última pasta preferida.
- **Progresso** — pode ser interrompido; o log reporta mensagens do codificador.

:::figure{side=block width=630}
![Painel de exportação de vídeo]({{img:workspace.image_compare.video.export_encode}})
{{tr:image_compare.action.video_editor}} — exportação.
:::

### {{tr:video.manual_cli}} {#manual-cli}

A aba {{tr:video.manual_cli}} passa argumentos brutos de saída do FFmpeg quando a aba padrão não basta. Prefira a aba padrão a menos que você conheça as flags necessárias.

### Próximos tópicos {#next-topics}

Imagens estáticas: [Exportação](help://export). Diferença e lupa durante a gravação acompanham o canvas ao vivo — [Comparação](help://comparison) e [Lupa](help://magnifier).
