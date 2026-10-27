---
description: Avaliar nitidez e exposição por pontuações numéricas.
icon: analyze.svg
---
## Métricas de qualidade

Cada imagem recebe uma pontuação de 0 a 100, e quanto maior, melhor. A pontuação resume várias medições da imagem, então uma pontuação alta significa que a imagem se sai bem em todas elas.

### Métricas medidas {#measured-metrics}

A pontuação combina nitidez, exposição, ruído e cor e, quando uma origem é definida, também o quão próxima a imagem está dela. A **Visualização rápida** lista cada leitura como porcentagem; uma leitura que o aplicativo não conseguiu obter aparece como **— · não medido**, nunca como zero. Com **IA** ligado, essas leituras são a própria análise da IA; com **Algoritmos** ligado, são as medições do aplicativo.

Uma leitura cuja variação em toda a série fica dentro do próprio ruído do instrumento de medição aparece como **não separa estas variantes** em vez de uma porcentagem: a linha permanece, mas essa leitura não consegue ordenar estas imagens e não tem peso no ranking.

### Eixos escolhidos pela IA {#judge-axes}

Quando a IA escolhe os eixos de uma série, a Visualização rápida mostra cada eixo nomeado pelo seu nome curto e legível; passe o cursor sobre a linha para ler a definição desse eixo e o rótulo **medido pela IA**. As leituras do registro mantêm os nomes de sempre.

- Um eixo nomeado pela IA mas não pontuado aparece como **— · não medido**: a linha não desaparece e nenhum zero é inventado.
- Um eixo que não muda ao longo da série aparece como **não separa estas variantes**.
- No cartão, o ponto de um eixo nomeado pela IA traz o mesmo rótulo **medido pela IA** ao passar o cursor e uma cor diferente das faixas medidas.

### Onde as pontuações aparecem {#where-scores}

- **Visualização rápida** — o painel aberto por um clique em um cartão; ele mostra uma linha por leitura e sua porcentagem.
- **Tira da Visualização rápida** — `←` / `→` (ou os círculos ‹ / ›) movem o foco pela tira e `Enter` mostra essa imagem. `↓` leva o foco aos botões de ação do painel (**Definir como origem** / **Rejeitar** / **Excluir**); `←` / `→` escolhem um e `Enter` o aciona; `↑` volta para a tira.
- **Pontos do cartão** — um ponto por métrica da pasta; o ponto fica verde (70 %+), âmbar (40–69 %) ou vermelho (abaixo de 40 %) conforme a leitura piora. Passe o cursor sobre um ponto para ver o nome da métrica e a porcentagem.
- **Qualidade da IA** — um valor de **Ordenar por** que ordena as imagens primeiro pela pontuação de IA; aplica-se apenas enquanto **IA** está ligado, e imagens sem pontuação vão para o fim.

:::figure{side=block width=100%}
![Painel Visualização rápida](../assets/quality_quicklook.png)
**Visualização rápida**: a imagem à esquerda e, à direita, os dados do arquivo mais uma linha por leitura com uma porcentagem ou **— · não medido**.
:::

### Modos {#modes}

A galeria escolhe um modo para a pasta, e o modo decide quais métricas os pontos do cartão mostram.

Quando uma imagem é definida como origem, a pontuação também mede o quão próxima cada imagem está dela; a origem é sempre escolhida manualmente, nunca automaticamente. Sem uma origem, a galeria trata a pasta como fotos de câmera ou como um lote sintético.

### Origem de referência {#reference-source}

**Origem** — a imagem escolhida como referência da comparação.

**Definir como origem** define essa referência; a análise então é executada novamente contra ela, e as pontuações seguem a nova referência na próxima passagem.
