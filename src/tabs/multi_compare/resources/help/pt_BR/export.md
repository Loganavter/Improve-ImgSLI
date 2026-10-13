## Salvar e exportar

A grade é salva como uma única imagem por meio do salvamento rápido ou do diálogo de salvamento. Uma sessão mantém sua grade, então reabrir a sessão traz o layout de volta.

### Salvamento e exportação {#save-and-export}

- **Salvamento rápido** (`Ctrl+S`) — grava a imagem com as configurações usadas por último, sem diálogo.
- **Salvar grade** — abre o diálogo de salvamento por meio de **Localizar ação**; veja [Exportação](help://workspace.export).
- **Resultado** — a imagem salva mostra a grade como ela aparece na tela.
- **Recorte** — o recorte de cada slot é aplicado antes de os slots serem combinados.
- **Slots vazios** — slots sem imagem ficam de fora da imagem salva.
- **Exportações grandes** — se o lado maior tiver mais de 16384 px, um aviso pergunta se deve continuar, porque tamanhos maiores não foram testados e a exportação pode falhar ou ficar sem memória. **Cancelar** interrompe a exportação; **Não mostrar novamente** desativa o aviso para exportações futuras.

### Sessões {#sessions}

Uma sessão armazena os caminhos e rótulos das imagens dos slots, o layout, o slot em foco, o zoom e a panorâmica, e o estilo dos rótulos e divisores. Os arquivos de imagem em si não são copiados; a sessão os reabre a partir de seus caminhos no disco.

- **Reabertura** — uma sessão mostra seus slots ao abrir. Suas imagens carregam novamente a partir de seus caminhos de arquivo; uma sessão que não está ativa carrega suas imagens quando você muda para ela.
- **Novas sessões** — uma nova sessão começa com o estilo de divisor e rótulo usado por último.
