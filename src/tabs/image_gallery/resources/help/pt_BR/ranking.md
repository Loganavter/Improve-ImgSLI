---
description: Os algoritmos classificam pela qualidade medida; o interruptor IA adiciona uma classificação marcada.
icon: algorithms.svg
---
## Classificação: Algoritmos e IA

Cada série recebe uma classificação — qual imagem é melhor. O interruptor na barra de ferramentas entre **Algoritmos** e **IA** decide quem classifica.

### Algoritmos {#algorithms}

O classificador padrão. Ele combina as leituras medidas numa única ordem determinística: as mesmas imagens com as mesmas leituras dão sempre a mesma classificação, e os empates são desempatados pelo caminho do arquivo, nunca pela ordem em que a pasta foi carregada. Quais leituras contam depende da pasta — veja [Métricas de qualidade](help://workspace.image_gallery.quality#modes).

- Uma imagem sem medições não mostra um número de classificação.
- A classificação ordena imagens apenas dentro de uma série.

### IA {#ai}

Opcional. Quando **IA** está ligado, a IA classifica a série a partir da própria leitura de qualidade de cada imagem, e não das medições do aplicativo. Essa classificação não é fixa: a mesma série pode voltar em outra ordem, e a faixa de estatísticas mostra **Classificado por IA (Jev)** para você nunca confundi-la com a leitura de **Algoritmos**.

- A classificação é salva por série, então uma nova execução é estável até a série mudar.
- Quando a IA está indisponível ou indecisa, a classificação volta a **Algoritmos** com o motivo mostrado, então a classificação nunca muda sem uma causa visível.

### Lendo a classificação {#badge}

- Um cartão mostra seu número de classificação; a vencedora de uma série mostra **★ BEST** no lugar de um número.
- A faixa de estatísticas mostra qual classificador produziu os números: **Classificado por Algoritmos**, **Classificado por IA (Jev)** ou **Classificado por Manual** quando você escolhe o vencedor com **Manter o melhor** / **Marcar como melhor**.
- Uma imagem sem classificação não mostra número.

### Próximos tópicos {#next-topics}

- [Métricas de qualidade](help://workspace.image_gallery.quality) — o que significam as leituras por trás da classificação dos Algoritmos.
- [Perguntar à IA](help://workspace.image_gallery.ask_ai) — faça perguntas sobre uma seleção ou uma série.
