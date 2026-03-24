## Navegação no Canvas

Esta aba descreve o trabalho com a visualização principal do canvas: zoom, pan e comportamento temporário dos overlays durante a navegação.

### Zoom
- Segure `Ctrl` e use a roda do mouse sobre o canvas para ampliar ou reduzir.
- O zoom é centrado no cursor, então você pode aproximar rapidamente a área desejada.
- Os rótulos com nomes de arquivo no canvas são mostrados apenas em **100% de zoom**. Em qualquer outro nível, eles ficam temporariamente ocultos e voltam automaticamente quando o zoom retorna para **100%**.

### Panorâmica
- Quando o zoom está acima de `100%`, segure o **botão do meio do mouse** e arraste para mover a visualização.
- A panorâmica acontece dentro da mesma janela, sem um modo separado.

### Linha Divisória Durante o Zoom
- A linha de comparação mantém sua posição visual na tela mesmo durante o zoom.
- Isso permite ampliar uma área e continuar trabalhando com o divisor sem saltos bruscos.

### Pré-visualização de Uma Imagem
- A pré-visualização rápida com `Espaço + Botão Esquerdo / Botão Direito` continua sendo a forma mais rápida de ver apenas um lado.
- Alguns overlays e rótulos podem simplificar ou ocultar temporariamente durante o zoom por motivos de desempenho.

### O Que É Controlado pelas Configurações
- Em **Configurações** você pode ajustar:
  - a resolução do display cache do preview;
  - o método principal de interpolação;
  - um método separado de interpolação durante movimento;
  - a otimização de movimento da lupa;
  - o cálculo automático de PSNR / SSIM.
- Se o preview parecer pesado demais ou suave demais, estes são os primeiros parâmetros a verificar.
