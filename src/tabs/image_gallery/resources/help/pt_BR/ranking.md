---
description: Os algoritmos classificam pela qualidade medida; o domínio IA adiciona um ranking Jev marcado.
icon: algorithms.svg
---
## Classificação: Algoritmos e IA

Cada série recebe uma classificação — qual imagem é melhor. O interruptor **Algoritmos | IA** na barra de ferramentas decide quem classifica.

### Algoritmos {#algorithms}

O padrão. Funde todas as leituras de qualidade medidas (nitidez, exposição, ruído, cor, correspondência com a fonte e as pontuações perceptuais aprendidas) numa única ordem determinística. As mesmas imagens com as mesmas leituras dão sempre a mesma classificação; os empates são desempatados pelo caminho do arquivo, nunca pela ordem em que a pasta foi carregada.

- Uma imagem sem nada medido fica **sem classificação** — sem número, nunca `#0`.
- A classificação ordena imagens apenas dentro de uma série.

### IA (Jev) {#ai}

Opcional. No domínio IA, o assistente **Jev** classifica a série a partir da própria leitura de qualidade da IA para cada imagem — as pontuações por eixo que a IA atribui, não as leituras dos detectores. Essa classificação é **marcada** e **não determinística**: a mesma série pode voltar em outra ordem, e o selo indica **IA (Jev)** para você nunca confundi-la com a leitura dos Algoritmos.

- Ela é armazenada em cache e fixada por série, então uma nova execução é estável até a série mudar.
- Quando o Jev está indisponível ou indeciso, ele **degrada visivelmente** para a classificação dos Algoritmos, e o motivo é mostrado — a classificação nunca muda de dono em silêncio.
- **Lotes grandes perguntam antes.** Com o domínio IA ativo, soltar mais de 35 imagens de uma vez mostra um aviso antes do envio — um lote grande pode significar uma conta alta de API. Escolha **Confirmar**, **Confirmar e não perguntar novamente** ou **Cancelar**.

### Lendo o selo {#badge}

O selo de classificação indica o classificador: **Algoritmos**, **IA (Jev)** ou **Manual** quando você mesmo escolhe o vencedor com **Manter melhor** / **Tornar melhor**. Uma imagem sem classificação não mostra número.

### Próximos tópicos {#next-topics}

- [Métricas de qualidade](help://workspace.image_gallery.quality) — o que significam as leituras por trás da classificação dos Algoritmos.
- [Perguntar à IA](help://workspace.image_gallery.ask_ai) — faça perguntas sobre uma seleção ou uma série.
