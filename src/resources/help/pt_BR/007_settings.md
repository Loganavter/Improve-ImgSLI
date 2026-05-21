## Configurações

Esta página agrupa as configurações por propósito em vez de repetir toda a interface como uma lista plana.

### Interface {#interface}
- **Idioma** altera o idioma do aplicativo.
- **Tema** alterna entre aparência clara, escura e automática.
- **Fonte da Interface** seleciona a fonte integrada, do sistema ou uma fonte personalizada instalada.
- **Comprimento Máximo do Nome (UI)** limita o tamanho dos rótulos na interface.
- **Modo da UI** muda não apenas a complexidade, mas também a forma como a barra de ferramentas foi pensada para uso.

### Modos da UI {#ui-modes}
- **Iniciante**:
  - é o modo mais simples;
  - mantém a interface mais orientada ao mouse;
  - serve bem para o primeiro uso e comparações básicas rápidas.
- **Avançado**:
  - expõe mais controles diretamente na tela;
  - serve para quem quer mudar parâmetros com mais frequência sem passos extras.
- **Especialista**:
  - torna a interface mais minimalista;
  - depende mais do controle por teclado, incluindo `WASD` e `QE`;
  - libera o máximo possível de espaço na tela para a imagem.

### Quando Trocar de Modo {#when-to-switch-modes}
- Se a interface parecer sobrecarregada, experimente **Iniciante** ou **Especialista**, dependendo do seu fluxo.
- Se você quiser mais controles visíveis ao mesmo tempo, use **Avançado**.
- Se prefere um fluxo baseado em teclado e quer mais espaço para o canvas, use **Especialista**.

### Preview e Qualidade {#preview-and-quality}
- **Resolução do Cache de Exibição** limita a resolução do preview principal para melhorar o desempenho.
- A lupa e a exportação final continuam usando a qualidade original.
- O método principal de interpolação afeta a qualidade da imagem estática.
- O método separado de interpolação durante movimento é usado apenas em cenários interativos quando a otimização está ativa.

### Lupa e Movimento Interativo {#magnifier-and-interactive-motion}
- **Otimizar movimento da lupa** ativa um modo mais rápido durante o movimento.
- **Destacar interseções de lupas** mostra sobreposição entre áreas de captura.
- **Colorir novas lupas automaticamente** ajuda a distinguir múltiplas instâncias.

### Análise e Métricas {#analysis-and-metrics}
- **Calcular automaticamente PSNR / SSIM** ativa métricas automáticas abaixo da área de comparação.
- Ela fica desativada por padrão para manter o preview mais leve.

### Carregamento e Fluxo de Trabalho {#loading-and-workflow}
- **Cortar automaticamente bordas pretas ao carregar** remove barras pretas nas bordas ao carregar arquivos.

### Sistema e Depuração {#system-and-debugging}
- **Notificações do sistema** controlam notificações após salvar.
- **Habilitar logs de depuração** adiciona logs detalhados para troubleshooting.

### O Que É Configurado em Outro Lugar {#configured-elsewhere}
- **Preview Quality** do editor de vídeo é alterado dentro do próprio **[editor de vídeo](help://export#video-editor-preview-quality)**.
- As opções específicas de saída são escolhidas no diálogo de **[Exportação](help://export#saving-an-image)**.
