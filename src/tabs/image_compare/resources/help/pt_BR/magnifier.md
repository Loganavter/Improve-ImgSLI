## Lupa

A **Lupa** amplia uma região escolhida do par comparado e mostra essa vista ampliada no canvas, para examinar detalhes que a linha divisória não revela.

### Ativar {#enabling}

- **Alternar lupa** — liga e desliga a lente pela barra de ferramentas ou pela tecla `M`.
- **Posicionar** — clique ou arraste sobre a imagem para escolher a área de captura, marcada por um círculo vermelho; é essa região que aparece ampliada.
- **Anel** — o tamanho e a cor do anel de captura seguem o estilo da lente, para você identificar a área amostrada.

:::figure{side=block width=280}
![Lente da lupa](../assets/magnifier.jpg)
A lente da lupa no canvas e o anel de captura vermelho que marca a área amostrada.
:::

### Tamanho e movimento {#size-and-movement}

- **Tam. Lupa (%)** — define o tamanho da vista ampliada sobre o canvas; quanto maior, mais a imagem é ampliada.
- **Tam. Captura (%)** — define quanto da área de origem é amostrada; ampliar a captura abrange uma região maior e reduz o aumento efetivo.
- **Mover** — com a lente ativa, `WASD` desloca a lente; `QE` ajusta o espaçamento entre as metades quando elas estão separadas.
- **Velocidade de Movimento** — define a rapidez com que a lente se desloca ao usar `WASD`; o controle fica no painel da lupa, quando ele está visível.

### Congelar {#freeze}

**Congelar lupa** (`F`) fixa a lente na posição atual do canvas: a área de captura continua se movendo, mas a vista ampliada fica parada. O teclado ainda desloca a lente congelada.

### Divisor, guias e cores {#guides-and-colors}

- **Orientação da lupa** — define se a lente divide a vista na horizontal ou na vertical.
- **Divisor da lupa** — o divisor interno da lente; ajuste-o com a rolagem e o clique direito.
- **Visibilidade do divisor da lupa** e **Guias da lupa** — mostram ou ocultam o divisor interno e as guias de alinhamento; as larguras são definidas à parte.
- **Cores da lupa** — define a cor do contorno de cada instância, para distinguir as lentes entre si.

### Várias instâncias {#instances}

- **Instâncias da lupa** — adicione ou remova lentes para observar várias regiões do par ao mesmo tempo.
- **Cor automática** — com **Colorir novas lupas automaticamente** ligado nas Configurações, cada nova instância recebe uma cor distinta.

### Modo combinado {#combined-mode}

- **Mesclar** — quando as duas metades seguem visíveis e o espaçamento entre elas cai abaixo do limiar de combinação, elas viram uma única lente.
- **Divisão interna** — arraste com o botão direito do mouse dentro da lente para reposicionar a divisão.
- **Pré-visualização de lado** — `Shift+Space` força a exibição de um dos lados dentro da lente combinada.

:::figure{side=block width=280}
![Lupa combinada](../assets/magnifier_combined.jpg)
Alternar lupa modo combinado.
:::

Para comparar o canvas inteiro sem a lente, veja [Comparação](help://workspace.image_compare.comparison).

### Configurações que afetam a lupa {#related-settings}

Opções relacionadas à lupa em [Configurações](help://platform.settings#image_compare):

- **Movimento da lupa** — suaviza o deslocamento da lente e a interpolação entre os quadros, para o movimento parecer contínuo.
- **Destaque vermelho para lupas sobrepostas** — marca em vermelho a área em que duas lentes se cruzam, para você notar a sobreposição.
- **Colorir novas lupas automaticamente** — dá uma cor distinta a cada nova lente, para separar as instâncias.
