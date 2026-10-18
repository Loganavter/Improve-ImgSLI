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

### Configuração e limites {#setup}

- **Galeria — IA** — a seção de configurações por trás de Perguntar à IA; perguntar exige **Ativar análise de imagem por IA**, uma **Chave de API** e um **Nome do modelo**. Configure em [Configurações](help://platform.settings#image-gallery-ai). Sem os três, o aplicativo mostra **Configure a chave de API de IA nas Configurações primeiro.**
- Enquanto o modelo trabalha, o painel mostra **Pensando…**; uma requisição malsucedida informa **A IA não conseguiu responder.**
- As respostas nunca alteram o ranking, a seleção ou qualquer estado armazenado.
- A mesma pergunta reutiliza a resposta em cache; um novo modelo ou novas imagens perguntam ao modelo novamente.
