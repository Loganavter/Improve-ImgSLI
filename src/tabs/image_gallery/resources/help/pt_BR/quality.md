---
description: Avaliar nitidez e exposição por pontuações numéricas.
icon: analyze.svg
---
## Métricas de qualidade

Cada imagem recebe uma pontuação de 0 a 100, e quanto maior, melhor. A pontuação resume várias medições da imagem, então uma pontuação alta significa que a imagem se sai bem em todas elas.

### Métricas medidas {#measured-metrics}

A pontuação combina nitidez, exposição, ruído e cor e, quando uma origem é definida, também o quão próxima a imagem está dela. A **Visualização rápida** lista cada leitura como porcentagem; uma leitura que o aplicativo não conseguiu obter aparece como **not measured**, nunca como zero. No domínio **IA**, essas leituras são a própria análise da IA; em **Algoritmos**, são as medições do aplicativo.

### Onde as pontuações aparecem {#where-scores}

- **Visualização rápida** — abre um painel com uma linha por leitura e sua porcentagem.
- **Pontos do cartão** — um ponto por métrica medida no modo atual; o ponto fica verde (70 %+), âmbar (40–69 %) ou vermelho (abaixo de 40 %) conforme a leitura piora. Passe o cursor sobre um ponto para ver o nome da métrica e a porcentagem.
- **AI quality** — um valor de **Sort by** que ordena as imagens primeiro pela pontuação de IA; aplica-se apenas enquanto o interruptor **IA** da barra de ferramentas está ligado, e imagens sem pontuação vão para o fim.

:::figure{side=block width=100%}
![Painel Visualização rápida](../assets/quality_quicklook.png)
**Visualização rápida**: a imagem à esquerda e, à direita, os dados do arquivo mais uma linha por leitura com uma porcentagem ou **not measured**.
:::

### Modos {#modes}

A galeria escolhe um modo para a pasta, e o modo decide quais métricas os pontos do cartão mostram.

Quando uma imagem é definida como origem, a pontuação também mede o quão próxima cada imagem está dela; a origem é sempre escolhida manualmente, nunca automaticamente. Sem uma origem, a galeria trata a pasta como fotos de câmera ou como um lote sintético.

### Origem de referência {#reference-source}

**Origem** — a imagem escolhida como referência da comparação.

**Definir como origem** define essa referência; a análise então é executada novamente contra ela, e as pontuações seguem a nova referência na próxima passagem.
