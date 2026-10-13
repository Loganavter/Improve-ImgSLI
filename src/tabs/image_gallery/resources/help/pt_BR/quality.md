## Métricas de qualidade

Cada imagem recebe uma pontuação de 0 a 100, e quanto maior, melhor. A pontuação resume várias medições da imagem, como nitidez, exposição, ruído e cor; assim, uma pontuação alta significa que a imagem se sai bem em todas elas.

### Métricas medidas {#measured-metrics}

A pontuação combina medições técnicas da imagem, incluindo como ela se compara com a origem quando uma está definida. A **Visualização rápida** mostra as leituras brutas por trás de cada pontuação. Quando a análise de imagem por IA está ativada, uma leitura de composição também é adicionada.

### Onde as pontuações aparecem {#where-scores}

- **Visualização rápida** — abre um painel com as linhas de métricas e as leituras brutas de uma imagem.
- **Pontos do cartão** — cada cartão mostra um pequeno marcador por verificação de artefato, indicando se a verificação está limpa, leve ou sinalizada.
- **Qualidade da IA** — um valor de **Ordenar por** que ordena as imagens primeiro pela pontuação de IA; imagens sem pontuação vão para o fim.

### Modos {#modes}

**Fidelidade** descreve quão proximamente uma imagem corresponde à origem. Aplica-se apenas enquanto uma origem está definida, e a origem é sempre escolhida manualmente, nunca automaticamente.

Sem uma origem, a pasta é tratada como fotos de câmera ou como um lote sintético. O modo decide quais verificações de artefato se aplicam aos pontos do cartão.

### Origem de referência {#reference-source}

**Origem** é a imagem escolhida como referência de fidelidade.

**Definir como origem** define a referência de fidelidade; a análise de fidelidade então é executada novamente contra ela, e as pontuações seguem a nova referência na próxima passagem.
