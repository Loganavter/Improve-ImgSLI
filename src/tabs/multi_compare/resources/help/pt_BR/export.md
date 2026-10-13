---
description: Guardar a grade como imagem e mantê-la na sessão.
icon: save_icon.svg
---
## Exportação da Comparação múltipla

A grade é salva como uma única imagem, e a sessão mantém a grade, então ela volta quando a sessão é reaberta.

### Salvamento e exportação {#save-and-export}

- **Salvamento rápido** (`Ctrl+S`) — grava a imagem com as configurações usadas por último, sem diálogo.
- **Salvar grade** — abre o diálogo de salvamento por meio de **Localizar ação**; veja [Exportação](help://workspace.export).
- **Resultado** — a imagem salva mostra a grade como ela aparece na tela.
- **Crop** — o recorte de cada slot é aplicado antes de os slots serem combinados.
- **Slots vazios** — slots sem imagem ficam de fora da imagem salva.
- **Exportações grandes** — se o lado maior tiver mais de 16384 px, um aviso pergunta se deve continuar, porque tamanhos maiores não foram testados e a exportação pode falhar ou ficar sem memória. **Cancelar** interrompe a exportação; **Não mostrar novamente** desativa o aviso para exportações futuras.

### Sessões {#sessions}

Uma sessão armazena os caminhos e rótulos das imagens dos slots, o layout, o slot em foco, o zoom e a panorâmica, e o estilo dos rótulos e divisores. Os próprios arquivos de imagem não são copiados — a sessão os reabre a partir de seus caminhos no disco.

- **Reabertura** — uma sessão reaberta mostra seus slots de imediato e carrega suas imagens a partir de seus caminhos; uma sessão que não está ativa carrega suas imagens quando fica ativa.
- **Novas sessões** — uma nova sessão começa com o estilo de divisor e rótulo usado por último.
