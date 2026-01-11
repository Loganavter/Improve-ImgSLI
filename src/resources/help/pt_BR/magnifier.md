## Ferramenta Lupa

### Fundamentos
- Marque **"Usar Lupa"** para habilitá-la.
- **Clique/arraste** na imagem principal para definir o ponto de captura (círculo vermelho).
- **Congelar Lupa:** bloqueia a posição da lupa na tela. Quando congelada, você ainda pode mover a visualização com `WASD`.

### Controles
- **Controle deslizante Tamanho da Lupa:** controla o nível de zoom.
- **Controle deslizante Tamanho da Captura:** ajusta o tamanho da área sendo amostrada da imagem original.
- **Controle deslizante Velocidade de Movimento:** define a velocidade para movimento com teclado.
- **Teclado `WASD`:** move a visualização ampliada em relação ao ponto de captura (ou move toda a lupa congelada).
- **Teclado `QE`:** ajusta o espaçamento entre as duas metades da lupa quando elas estão separadas.
- **Interpolação:** escolha um método de reamostragem (ex.: Vizinho Mais Próximo, Bilinear, Lanczos, EWA Lanczos) para controlar a qualidade de renderização da imagem ampliada.
  - **EWA Lanczos:** um método avançado usando supersampling para simular EWA (Elliptical Weighted Average) Lanczos. Fornece anti-aliasing superior primeiro aumentando a imagem 2×, depois diminuindo com filtragem Lanczos. Excelente para reduzir moiré e aliasing em imagens detalhadas.


### Renderização de Alta Precisão
- A lupa usa renderização de subpixels para garantir comparações suaves e precisas, mesmo quando as duas imagens têm resoluções diferentes.
- Isso elimina a trepidação de pixels ao mover o ponto de captura e fornece uma visualização mais precisa dos detalhes.


### Metades Combinadas e Divisão Interna
- Quando o espaçamento entre as duas metades da lupa fica pequeno o suficiente, ou quando um modo de diferenças está ativo, as metades se combinam automaticamente em um único círculo com uma linha de divisão interna.
- Você pode ajustar a posição da divisão interna arrastando com o Botão Direito do Mouse dentro do círculo da lupa.

### Linhas Guia ("Lasers")
- Para conectar visualmente a lupa ao seu ponto de captura na imagem principal, você pode habilitar linhas guia.
- Clique no botão com ícone de laser na barra de ferramentas da lupa para ativá-las ou desativá-las.
- A espessura dessas linhas pode ser ajustada rolando a roda do mouse sobre o mesmo botão.

### Menu de Visibilidade (Esquerda/Centro/Direita)
- Passe o mouse sobre o botão da Lupa para revelar um pequeno menu que permite alternar a visibilidade das partes esquerda, central e direita.
- Você também pode abrir este menu rolando a roda do mouse sobre o botão da Lupa; neste caso, ele se oculta automaticamente após um curto período.
- A alternância do Centro está disponível apenas quando um modo de diferenças está ativo.

### Alternância Rápida de Orientação
- Clique com o botão direito no botão principal de Orientação para alternar rapidamente a orientação da divisão da lupa. Um pequeno indicador popup confirmará a orientação atual.

### Controles da Divisória da Lupa
- Espessura da divisória (dentro da lupa): role a roda do mouse sobre o botão de Espessura da Divisória da Lupa para ajustar a espessura. Um pequeno popup numérico mostra o valor atual.
- Cor da divisória (dentro da lupa): clique no botão de Cor da Divisória da Lupa para escolher uma cor.

### Otimização de Performance
- Para uma experiência mais suave ao mover a lupa (arrastando o ponto de captura ou usando as teclas WASD), você pode habilitar **"Otimizar movimento da lupa"** nas Configurações.
- Isso usa um método de interpolação mais rápido e de menor qualidade durante o movimento, enquanto o método de alta qualidade selecionado na interface principal é usado assim que a lupa para.
