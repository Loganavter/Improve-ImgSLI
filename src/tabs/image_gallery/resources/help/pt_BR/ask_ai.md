---
description: Receber comentários da IA sobre uma foto, seleção ou série.
icon: ai.svg
---
## Perguntar à IA

**Perguntar à IA** responde a perguntas sobre um único cartão, a seleção atual ou uma série inteira. As respostas são consultivas, e toda resposta carrega o selo **Leitura de IA, não verificada**.

### Perguntar sobre uma seleção {#ask-selection}

- **IA…** — abre **Perguntar à IA** para esse cartão ou a seleção atual.
- **O que importa aqui?** — a pergunta padrão; pede ao modelo que resuma as imagens que recebe.
- **Leitura de IA, não verificada** — o selo em uma resposta; ele marca a resposta como não verificada.

:::figure{side=block width=420}
![Painel Perguntar à IA](../assets/ask_ai_panel.png)
O painel **Perguntar à IA**: o campo de pergunta, a resposta e o selo **Leitura de IA, não verificada**.
:::

### Perguntar sobre uma série {#ask-series}

O menu do cabeçalho da série pergunta de uma vez sobre cada membro da série. A pergunta carrega as leituras medidas — veja [Métricas de qualidade](help://workspace.image_gallery.quality).

### Histórico e barra lateral {#history-sidebar}

- **Histórico** — o painel lista as perguntas já respondidas no registro de perguntas e respostas, as mais novas por último; cada entrada mostra a pergunta e a resposta.
- Selecionar uma entrada mostra novamente a resposta guardada — nenhuma nova requisição à IA é feita.
- O botão **IA** da barra de ferramentas mostra ou oculta a barra lateral **Perguntar à IA**: a mesma superfície de pergunta, ancorada ao lado da grade em vez de uma janela pop-up. **✕** fecha a barra; as setas alcançam o botão e cada linha do histórico.

### Configuração e limites {#setup}

- **Galeria — IA** — a seção de configurações por trás de Perguntar à IA; perguntar exige **Ativar análise de imagem por IA**, uma **Chave de API** e um **Nome do modelo**. Configure em [Configurações](help://platform.settings#image-gallery-ai). Sem os três, o aplicativo mostra **Configure a chave de API de IA nas Configurações primeiro.**
- Enquanto o modelo trabalha, o painel mostra **Pensando…**; uma requisição malsucedida informa **A IA não conseguiu responder.**
- As respostas nunca alteram o ranking, a seleção ou qualquer estado armazenado.
- A mesma pergunta reutiliza a resposta em cache; um novo modelo ou novas imagens perguntam ao modelo novamente.

### Quanto custa uma execução do juiz {#cost}

A mesma seção **Galeria — IA** guarda os dois limites da análise de uma série, em [Configurações](help://platform.settings#image-gallery-ai):

- **Solicitações paralelas ao juiz de IA** — quantas solicitações o juiz de IA pode manter em andamento ao mesmo tempo; cada faixa paralela é mais uma solicitação enviada ao provedor no mesmo momento.
- **Limite de chamadas por execução do juiz** — o máximo de chamadas que uma execução pode fazer; **ilimitado** significa que a execução não tem teto. Uma execução faz até k chamadas por cartão, em que k é **Execuções por cartão**, portanto uma série de 10 cartões com 3 execuções custa até 30 chamadas.
- **Refinar quase-empates por comparação em pares** — ordena os melhores pela nota individual com perguntas “A ou B” em vez de mais execuções por cartão; uma passagem custa até N × (N−1) chamadas (N = 5 por padrão, ou seja, 10 pares e até 20 chamadas) e é totalmente ignorada quando a diferença das notas individuais nesse conjunto já passa do limite de quase-empate.
