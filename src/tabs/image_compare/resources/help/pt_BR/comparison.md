## Comparação

Compare duas imagens no canvas inteiro com um divisor móvel: arraste a fronteira, exiba os nomes dos arquivos, isole canais de cor e veja os modos de diferença, tudo sem abrir a **Lupa**.

### Linha divisória {#split-line}

Com a **Lupa** desligada, arraste o divisor sobre o par para ajustar a fronteira entre as duas imagens.

- **Orientação** — o controle **Orientação da divisão** alterna o divisor entre horizontal e vertical, para colocar as imagens lado a lado ou uma sobre a outra.
- **Largura** — gire a roda do mouse sobre **Largura do divisor** para engrossar ou afinar a linha; em imagens detalhadas, uma linha mais larga ajuda a localizar a fronteira.
- **Cor** — **Cor do divisor** define a cor da linha, para destacá-la do conteúdo das imagens.
- **Visibilidade** (`D`) — **Visibilidade do divisor** mostra ou oculta a linha; a tecla `D` alterna sem tirar as mãos do teclado.
- **Combinado** — o controle **Divisor** reúne **Orientação da divisão**, **Largura do divisor** e **Cor do divisor**; a rolagem, o clique direito e o clique do meio o ajustam sem abrir o painel.

:::figure{side=block width=280}
![Linha divisória](../assets/split_line.png)
A linha divisória no canvas: arraste-a para revelar o mesmo ponto dos dois lados.
:::

### Percorrer imagens com a rolagem {#scroll-images}

- **Rolar o canvas** — a rolagem avança a lista do lado sob o cursor: à esquerda de um divisor vertical, ou acima de um horizontal, você percorre o lado 1; na outra metade, o lado 2.
- **`Shift` + rolagem** — rola as duas listas ao mesmo tempo, para manter a mesma imagem nos dois lados.
- **Pré-visualização de uma imagem** — a rolagem avança sempre o lado visível, mesmo durante a pré-visualização.
- **Rolar o menu suspenso** — muda a imagem daquele lado sem abrir o painel da lista.
- **Trocar** (`X`) — um clique curto troca o par atual e um pressionamento longo troca as duas listas, para recomeçar a comparação rapidamente.

### Rótulos {#labels-and-metrics}

- **Mostrar nomes** (`N`) — o controle **Sobreposição de nomes** exibe o nome do arquivo sobre cada imagem; os nomes podem ser gravados nas exportações quando a sobreposição está ativa.
- **Zoom** — os rótulos ficam ocultos enquanto o zoom não está em `100%` e reaparecem no zoom de ajuste, para não cobrir os detalhes ampliados.
- **Configurações de texto** — o painel **Configurações de texto do rótulo** ajusta tamanho, peso, opacidade, cores, fundo e posicionamento dos rótulos.

### Métricas {#metrics}

- **PSNR** e **SSIM** — desligados por padrão; mostram a semelhança numérica entre as imagens. Ative **Calcular PSNR automaticamente** ou **Calcular SSIM automaticamente** nas [Configurações](help://platform.settings).
- **Propriedades** — [Propriedades da imagem](help://platform.image_properties) abre pelo menu de contexto de uma linha da lista e mostra os metadados do arquivo, o lado e a avaliação na sessão.

### Mover uma imagem entre abas {#moving-between-tabs}

1. No menu de contexto da imagem (no canvas ou na lista), escolha **Mover**.
2. Ao lado do cursor aparece uma cópia semitransparente da imagem.
3. Clique na aba desejada da área de trabalho ou no canvas para inserir a imagem, do mesmo modo que ao duplicar ou colar.
4. Para cancelar, pressione `Esc` ou clique com o botão direito.

### Modos de canal {#channel-modes}

**Modo de canal** (`C`) alterna entre RGB, R, G, B e luminância, para inspecionar um canal de cor sem sair do canvas.

### Modos de diferença {#difference-modes}

**Modo de diferença** (`H` alterna) realça onde o par difere, para localizar mudanças sem ampliar:

:::figure{side=block width=280}
![Modo de diferença](../assets/difference_modes.png)
O mesmo par em cada modo: **Destaque**, escala de cinza, bordas e SSIM mostram as diferenças de formas distintas.
:::

- **Destaque** — realça com cor as regiões em que as imagens diferem.
- **Escala de cinza** — atenua as diferenças de intensidade, para revelar variações de brilho.
- **Bordas** — concentra a diferença nas bordas, útil para perceber contornos deslocados.
- **SSIM** — mostra um mapa de similaridade estrutural quando o cálculo de métricas está ativo.

O canvas ao vivo, as imagens exportadas e a gravação de vídeo mantêm a mesma aparência, e os modos de diferença combinam com os modos de canal. Para inspeção local, use a [Lupa](help://workspace.image_compare.magnifier).
