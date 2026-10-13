## Configurações

As Configurações reúnem as opções do aplicativo em um diálogo: páginas internas como **Geral** e **Aparência**, mais as seções contribuídas pelas abas. As seções das abas ficam visíveis seja qual for a sessão ativa.

### Abrir Configurações {#open-settings}

- **Menu** — **Configurações** (`Ctrl+,`).
- **Barra de ferramentas** — o botão de engrenagem.
- **Localizar ação** — `Ctrl+Shift+P` e o nome da página (Geral, Aparência, Teclado, …).
- **Saiba mais** — abre o tópico de ajuda da configuração, quando existe.

### Pesquisar nas Configurações {#search}

Um campo de pesquisa fica acima da lista. Cada seção correspondente aparece como uma única linha, não importa a profundidade do acerto (nome de controle, título de grupo, em qualquer idioma). Ativar uma linha abre a seção com os acertos destacados. `Esc` limpa a pesquisa e restaura a lista completa.

### Geral {#general}

- **Idioma** — escolhe o idioma da interface: en / ru / zh / pt_BR.
- **Tema** — auto / light / dark.
- **Notificações do sistema** — liga ou desliga as notificações do sistema operacional.
- **Ativar registro de depuração** — grava logs detalhados para diagnóstico.

### Aparência {#interface}

- **Modo da UI** — **Iniciante**, **Avançado** ou **Especialista**; o padrão é **Iniciante**, e a escolha da primeira abertura fica aqui.
- **Fonte da UI** — fonte interna, padrão do sistema ou personalizada.
- **Escala da interface** — redimensiona toda a interface (0,5–2,5).
- **Limites** — tetos para valores relacionados, como o comprimento máximo do nome exibido.

### Desempenho {#performance}

- **Backend** — backend de renderização. As opções dependem da plataforma, e trocar pode exigir reiniciar.

### Comparar imagens {#image_compare}

Opções do comparador, sempre disponíveis:

- **Interpolação** — define a qualidade de reamostragem do zoom e da lupa.
- **Movimento da lupa** — deixa o movimento da lente mais suave; o método de interpolação fica na mesma linha.
- **Destaque vermelho para lupas sobrepostas** — ao arrastar uma lupa, a parte do anel de captura escondida atrás de outras lupas é destacada.
- **Colorir novas lupas automaticamente** — dá cores distintas às novas lentes.
- **FPS de Gravação** — taxa de captura para o [Editor de vídeo](help://workspace.image_compare.video).
- **Cortar automaticamente bordas pretas ao carregar** — corta as bordas pretas quando uma imagem é carregada.
- **Calcular PSNR automaticamente** / **Calcular SSIM automaticamente** — mostram a métrica automaticamente; desligadas por padrão.

### Teclado {#keyboard}

- **Remapear** — agrupa os atalhos por dono: Plataforma / Comparar imagens / Comparação múltipla.
- **Redefinir** — redefine um atalho ou todos.
- **Fixos** — `WASD` e `Space` no canvas não podem ser remapeados — veja [Atalhos](help://platform.hotkeys).
