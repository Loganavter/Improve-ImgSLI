---
description: Avaliar nitidez e exposição por pontuações numéricas.
icon: analyze.svg
---
## Métricas de qualidade

Cada imagem recebe uma pontuação de 0 a 100, e quanto maior, melhor. A pontuação resume várias medições da imagem, então uma pontuação alta significa que a imagem se sai bem em todas elas.

### Métricas medidas {#measured-metrics}

A pontuação combina nitidez, exposição, ruído e cor e, quando uma origem é definida, também o quão próxima a imagem está dela. A **Visualização rápida** lista cada leitura como porcentagem; uma leitura que o aplicativo não conseguiu obter aparece como **not measured**, nunca como zero. Quando a análise de imagem por IA está ativada, uma leitura de composição se junta a elas.

### Onde as pontuações aparecem {#where-scores}

- **Visualização rápida** — abre um painel com uma linha por leitura e sua porcentagem.
- **Pontos do cartão** — três pontos em cada cartão, um por verificação de defeito; o ponto fica verde, âmbar ou vermelho conforme a verificação piora.
- **AI quality** — um valor de **Sort by** que ordena as imagens primeiro pela pontuação de IA; aplica-se apenas enquanto o interruptor **IA** da barra de ferramentas está ligado, e imagens sem pontuação vão para o fim.

### Modos {#modes}

A galeria escolhe um modo para a pasta, e o modo decide quais verificações de defeito os pontos do cartão mostram.

Quando uma imagem é definida como origem, a pontuação também mede o quão próxima cada imagem está dela; a origem é sempre escolhida manualmente, nunca automaticamente. Sem uma origem, a galeria trata a pasta como fotos de câmera ou como um lote sintético.

### Origem de referência {#reference-source}

**Origem** — a imagem escolhida como referência da comparação.

**Definir como origem** define essa referência; a análise então é executada novamente contra ela, e as pontuações seguem a nova referência na próxima passagem.
